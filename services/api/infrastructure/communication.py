import json
from dataclasses import asdict
from uuid import UUID, uuid4

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from services.api.application.agent_context import encode_context
from services.api.application.context import ActorContext
from services.api.application.ports.boss_page import (
    BossPageObservation,
    conversation_message_window,
    has_bound_conversation_messages,
)
from services.api.application.ports.communication import ReplyClaim, ReplyInput
from services.api.domain.communication import (
    CommunicationConflict,
    CommunicationInvalid,
    CommunicationNotFound,
    CommunicationReply,
    CommunicationUnavailable,
    ReplyDecision,
    ReplyPage,
)
from services.api.domain.memory import MemoryInvalid
from services.api.domain.profile import ProfileContent


def profile_facts(content: ProfileContent) -> dict[str, str]:
    result = {
        key: value
        for key, value in asdict(content).items()
        if key not in {"goals", "constraints"} and isinstance(value, str) and value.strip()
    }
    for section in ("education", "experience", "projects"):
        for index, entry in enumerate(getattr(content, section)):
            for field, value in asdict(entry).items():
                if isinstance(value, str) and value.strip():
                    result[f"{section}.{index}.{field}"] = value
    return result


def reply_from_row(row: RowMapping) -> CommunicationReply:
    return CommunicationReply(
        id=row["id"],
        user_id=row["user_id"],
        connection_id=row["connection_id"],
        read_task_id=row["read_task_id"],
        conversation_id=row["conversation_id"],
        message_id=row["message_id"],
        request_key=row["request_key"],
        version=row["version"],
        status=row["status"],
        outcome=row["outcome"],
        decision=TypeAdapter(ReplyDecision).validate_python(row["decision"])
        if row["decision"] is not None
        else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
    )


class PostgresCommunicationRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def accept(
        self,
        actor: ActorContext,
        *,
        connection_id: UUID,
        read_task_id: UUID,
        conversation_id: str,
        message_id: str,
        request_key: UUID,
    ) -> CommunicationReply:
        try:
            async with self.engine.begin() as db:
                connection = (
                    (
                        await db.execute(
                            text(
                                "SELECT * FROM career.boss_connections WHERE id=:connection "
                                "AND user_id=:user FOR UPDATE"
                            ),
                            {"connection": connection_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if connection is None:
                    raise CommunicationNotFound("Recruiting connection not found")
                existing = (
                    (
                        await db.execute(
                            text(
                                "SELECT * FROM career.communication_replies WHERE user_id=:user "
                                "AND request_key=:key"
                            ),
                            {"user": actor.user_id, "key": request_key},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing is not None:
                    if (
                        existing["connection_id"] != connection_id
                        or existing["read_task_id"] != read_task_id
                        or existing["conversation_id"] != conversation_id
                        or existing["message_id"] != message_id
                    ):
                        raise CommunicationConflict("Idempotency key has a different target")
                    return reply_from_row(existing)
                if connection["status"] != "connected":
                    raise CommunicationConflict("Read an active recruiting connection first")
                source_row = (
                    (
                        await db.execute(
                            text(
                                "SELECT p.page, p.observed_at FROM career.execution_tasks t "
                                "JOIN career.execution_resources r ON r.task_id=t.id AND "
                                "r.user_id=t.user_id "
                                "JOIN career.execution_read_results p ON p.task_id=t.id AND "
                                "p.user_id=t.user_id "
                                "WHERE t.id=:task AND t.user_id=:user AND t.kind='boss_read' "
                                "AND r.connection_id=:connection AND "
                                "r.conversation_id=:conversation "
                                "AND r.connection_version=:version AND t.status='completed' "
                                "AND p.observed_at > clock_timestamp()-interval '15 minutes' FOR "
                                "SHARE OF t"
                            ),
                            {
                                "task": read_task_id,
                                "user": actor.user_id,
                                "connection": connection_id,
                                "conversation": conversation_id,
                                "version": connection["version"],
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if source_row is None:
                    raise CommunicationConflict("A recent completed conversation read is required")
                page = TypeAdapter(BossPageObservation).validate_python(source_row["page"])
                if page.state != "ready" or not has_bound_conversation_messages(page):
                    raise CommunicationConflict("Conversation observation is not verified")
                messages = conversation_message_window(page, conversation_id)
                human_messages = [m for m in messages if m.sender in {"recruiter", "candidate"}]
                if (
                    not human_messages
                    or human_messages[-1].message_id != message_id
                    or human_messages[-1].sender != "recruiter"
                    or human_messages[-1].resume_attachment is not None
                ):
                    raise CommunicationConflict("Select the latest unanswered recruiter message")
                profile_row = (
                    (
                        await db.execute(
                            text(
                                "SELECT content, version FROM career.profiles WHERE user_id=:user "
                                "FOR SHARE"
                            ),
                            {"user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                facts = (
                    profile_facts(
                        TypeAdapter(ProfileContent).validate_python(profile_row["content"])
                    )
                    if profile_row
                    else {}
                )
                rules = (
                    (
                        await db.execute(
                            text(
                                "SELECT id, version, title, content FROM career.workspace_memories "
                                "WHERE user_id=:user AND kind='rule' AND state='confirmed' "
                                "AND project_id IS NULL ORDER BY id LIMIT 101 FOR SHARE"
                            ),
                            {"user": actor.user_id},
                        )
                    )
                    .mappings()
                    .all()
                )
                if len(rules) > 100:
                    raise CommunicationInvalid("Confirmed rules exceed the context limit")
                # No partial truncation of messages or effective rules; reject an oversized scope.
                payload: dict[str, object] = {
                    "messages": [{"sender": m.sender, "content": m.content} for m in messages],
                    "profile_facts": facts,
                    "confirmed_rules": [
                        {"title": r["title"], "content": r["content"]} for r in rules
                    ],
                }
                encode_context(payload)
                source = {
                    "payload": payload,
                    "profile_facts": facts,
                    "observed_at": source_row["observed_at"].isoformat(),
                    "connection_version": str(connection["version"]),
                    "profile_version": str(profile_row["version"]) if profile_row else None,
                    "rules": [{"id": str(r["id"]), "version": str(r["version"])} for r in rules],
                }
                await self._expire(db, actor.user_id)
                existing_source = (
                    (
                        await db.execute(
                            text(
                                "SELECT * FROM career.communication_replies WHERE user_id=:user "
                                "AND connection_id=:connection AND conversation_id=:conversation "
                                "AND message_id=:message AND status IN "
                                "('accepted','running','waiting','completed')"
                            ),
                            {
                                "user": actor.user_id,
                                "connection": connection_id,
                                "conversation": conversation_id,
                                "message": message_id,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing_source is not None:
                    raise CommunicationConflict("A reply decision already exists for this message")
                attempted = await db.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM career.communication_replies r "
                        "JOIN career.communication_sends s ON s.reply_id=r.id "
                        "WHERE r.user_id=:user AND r.connection_id=:connection "
                        "AND r.conversation_id=:conversation AND r.message_id=:message)"
                    ),
                    {
                        "user": actor.user_id,
                        "connection": connection_id,
                        "conversation": conversation_id,
                        "message": message_id,
                    },
                )
                if attempted:
                    raise CommunicationConflict(
                        "Reconcile the existing send before another decision"
                    )
                row = (
                    (
                        await db.execute(
                            text(
                                "INSERT INTO career.communication_replies "
                                "(id,user_id,connection_id,read_task_id,conversation_id,message_id,"
                                "request_key,version,source,expires_at) VALUES "
                                "(:id,:user,:connection,:task,:conversation,:message,:key,:version,"
                                "CAST(:source AS jsonb),clock_timestamp()+interval '15 minutes') "
                                "RETURNING *"
                            ),
                            {
                                "id": uuid4(),
                                "user": actor.user_id,
                                "connection": connection_id,
                                "task": read_task_id,
                                "conversation": conversation_id,
                                "message": message_id,
                                "key": request_key,
                                "version": uuid4(),
                                "source": json.dumps(source, ensure_ascii=False),
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                return reply_from_row(row)
        except MemoryInvalid:
            raise CommunicationInvalid("Reply context exceeds its bounded scope") from None
        except IntegrityError:
            raise CommunicationConflict("The message already has a reply task") from None
        except (DBAPIError, PoolTimeoutError, ValidationError):
            raise CommunicationUnavailable("Reply input storage is unavailable") from None

    async def get(self, actor: ActorContext, reply_id: UUID) -> CommunicationReply:
        try:
            async with self.engine.begin() as db:
                await self._expire(db, actor.user_id)
                row = (
                    (
                        await db.execute(
                            text(
                                "SELECT * FROM career.communication_replies WHERE id=:id AND "
                                "user_id=:user"
                            ),
                            {"id": reply_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise CommunicationNotFound("Reply task not found")
                return reply_from_row(row)
        except (DBAPIError, PoolTimeoutError, ValidationError):
            raise CommunicationUnavailable("Reply storage is unavailable") from None

    async def list(
        self, actor: ActorContext, connection_id: UUID, cursor: UUID | None = None
    ) -> ReplyPage:
        try:
            async with self.engine.begin() as db:
                owned = await db.scalar(
                    text("SELECT 1 FROM career.boss_connections WHERE id=:id AND user_id=:user"),
                    {"id": connection_id, "user": actor.user_id},
                )
                if not owned:
                    raise CommunicationNotFound("Recruiting connection not found")
                await self._expire(db, actor.user_id)
                boundary = ""
                parameters: dict[str, object] = {"user": actor.user_id, "connection": connection_id}
                if cursor is not None:
                    before = (
                        (
                            await db.execute(
                                text(
                                    "SELECT created_at,id FROM career.communication_replies "
                                    "WHERE id=:cursor AND user_id=:user "
                                    "AND connection_id=:connection"
                                ),
                                {**parameters, "cursor": cursor},
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if before is None:
                        raise CommunicationInvalid("Invalid reply cursor")
                    boundary = "AND (created_at,id)<(:before,:cursor) "
                    parameters.update({"before": before["created_at"], "cursor": cursor})
                rows = (
                    (
                        await db.execute(
                            text(
                                "SELECT * FROM career.communication_replies WHERE user_id=:user "
                                "AND connection_id=:connection "
                                + boundary
                                + "ORDER BY created_at DESC,id DESC LIMIT 21"
                            ),
                            parameters,
                        )
                    )
                    .mappings()
                    .all()
                )
                return ReplyPage(
                    tuple(reply_from_row(r) for r in rows[:20]),
                    rows[19]["id"] if len(rows) > 20 else None,
                )
        except (DBAPIError, PoolTimeoutError, ValidationError):
            raise CommunicationUnavailable("Reply list is unavailable") from None

    async def cancel(
        self, actor: ActorContext, reply_id: UUID, expected_version: UUID
    ) -> CommunicationReply:
        try:
            async with self.engine.begin() as db:
                row = (
                    (
                        await db.execute(
                            text(
                                "SELECT * FROM career.communication_replies WHERE id=:id "
                                "AND user_id=:user FOR UPDATE"
                            ),
                            {"id": reply_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise CommunicationNotFound("Reply task not found")
                if row["status"] == "cancelled":
                    return reply_from_row(row)
                if row["version"] != expected_version:
                    raise CommunicationConflict("Read the latest reply version before cancelling")
                if row["status"] not in {"accepted", "running", "waiting"}:
                    raise CommunicationConflict("A finished reply cannot be cancelled")
                if await db.scalar(
                    text("SELECT 1 FROM career.communication_sends WHERE reply_id=:id"),
                    {"id": reply_id},
                ):
                    raise CommunicationConflict("A send has been authorized; use its task controls")
                return reply_from_row(
                    (
                        await db.execute(
                            text(
                                "UPDATE career.communication_replies SET status='cancelled', "
                                "outcome='user_cancelled', version=:version,claim_token=NULL,"
                                "claim_expires_at=NULL,updated_at=clock_timestamp() WHERE id=:id "
                                "RETURNING *"
                            ),
                            {"id": reply_id, "version": uuid4()},
                        )
                    )
                    .mappings()
                    .one()
                )
        except (DBAPIError, PoolTimeoutError, ValidationError):
            raise CommunicationUnavailable("Reply cancellation is unavailable") from None

    async def _expire(self, db: AsyncConnection, user_id: str) -> None:
        await db.execute(
            text(
                "UPDATE career.communication_replies SET status='timed_out', "
                "outcome='decision_expired', "
                "version=:version,claim_token=NULL,claim_expires_at=NULL,"
                "updated_at=clock_timestamp() "
                "WHERE user_id=:user AND status IN ('accepted','running','waiting') "
                "AND expires_at<=clock_timestamp() AND NOT EXISTS "
                "(SELECT 1 FROM career.communication_sends s "
                "WHERE s.reply_id=career.communication_replies.id)"
            ),
            {"user": user_id, "version": uuid4()},
        )

    async def claim(self, reply_id: UUID) -> ReplyClaim | None:
        try:
            async with self.engine.begin() as db:
                await self._invalidate_connection(db, reply_id)
                token = uuid4()
                row = (
                    (
                        await db.execute(
                            text(
                                "UPDATE career.communication_replies SET status='running', "
                                "claim_token=:token,claim_expires_at=clock_timestamp()+interval "
                                "'90 seconds', "
                                "version=:version,updated_at=clock_timestamp() WHERE id=:id "
                                "AND expires_at>clock_timestamp() "
                                "AND (status='accepted' OR (status='running' "
                                "AND claim_expires_at<=clock_timestamp())) RETURNING *"
                            ),
                            {"id": reply_id, "token": token, "version": uuid4()},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return None
                source = TypeAdapter(ReplyInput).validate_python(
                    {
                        "payload": row["source"]["payload"],
                        "profile_facts": row["source"]["profile_facts"],
                    }
                )
                return ReplyClaim(reply_from_row(row), token, source)
        except (DBAPIError, PoolTimeoutError, ValidationError):
            raise CommunicationUnavailable("Reply claim is unavailable") from None

    async def finish(
        self, claim: ReplyClaim, *, decision: ReplyDecision | None, outcome: str
    ) -> None:
        status = (
            "failed"
            if decision is None
            else ("completed" if decision.category == "no_action" else "waiting")
        )
        try:
            async with self.engine.begin() as db:
                await self._invalidate_connection(db, claim.reply.id)
                await db.execute(
                    text(
                        "UPDATE career.communication_replies SET status=:status,outcome=:outcome,"
                        "decision=CAST(:decision AS jsonb),version=:version,claim_token=NULL,"
                        "claim_expires_at=NULL,updated_at=clock_timestamp() WHERE id=:id "
                        "AND user_id=:user AND status='running' AND claim_token=:token "
                        "AND claim_expires_at>clock_timestamp() AND expires_at>clock_timestamp()"
                    ),
                    {
                        "id": claim.reply.id,
                        "user": claim.reply.user_id,
                        "token": claim.token,
                        "status": status,
                        "outcome": outcome,
                        "version": uuid4(),
                        "decision": json.dumps(asdict(decision), ensure_ascii=False)
                        if decision is not None
                        else None,
                    },
                )
        except (DBAPIError, PoolTimeoutError):
            raise CommunicationUnavailable("Reply result persistence is unconfirmed") from None

    async def _invalidate_connection(self, db: AsyncConnection, reply_id: UUID) -> None:
        # Serialize source validation with login replacement/revocation. Retain the
        # connection lock through claim/finish, using the same lock order as accept.
        await db.execute(
            text(
                "SELECT c.id FROM career.boss_connections c "
                "JOIN career.communication_replies r ON r.connection_id=c.id "
                "AND r.user_id=c.user_id WHERE r.id=:id FOR SHARE OF c"
            ),
            {"id": reply_id},
        )
        await db.execute(
            text(
                "UPDATE career.communication_replies r SET status='cancelled', "
                "outcome='connection_changed', version=:version, claim_token=NULL, "
                "claim_expires_at=NULL, updated_at=clock_timestamp() "
                "WHERE r.id=:id AND r.status IN ('accepted','running') AND NOT EXISTS "
                "(SELECT 1 FROM career.boss_connections c WHERE c.id=r.connection_id "
                "AND c.user_id=r.user_id AND c.status='connected' "
                "AND c.version::text=r.source->>'connection_version')"
            ),
            {"id": reply_id, "version": uuid4()},
        )
