import json
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from services.api.application.context import ActorContext
from services.api.application.ports.boss_page import (
    BossPageObservation,
    has_bound_conversation_messages,
)
from services.api.application.ports.browser_control import BrowserControlContext
from services.api.application.ports.communication_send import SendClaim
from services.api.domain.communication import (
    CommunicationConflict,
    CommunicationNotFound,
    CommunicationUnavailable,
    ReplyDecision,
    is_factual_reply,
)
from services.api.domain.communication_send import CommunicationSend, SendEvidence
from services.api.infrastructure.communication import reply_from_row


def send_from_row(row: RowMapping) -> CommunicationSend:
    return CommunicationSend(
        row["task_id"],
        row["reply_id"],
        row["connection_id"],
        row["conversation_id"],
        row["message_id"],
        row["text"],
        row["status"],
        row["outcome"],
        row["expires_at"],
        row["evidence_message_id"],
        row["cleanup_required"],
    )


class PostgresSendRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def _get(
        self, db: AsyncConnection, user_id: str, reply_id: UUID
    ) -> CommunicationSend | None:
        row = (
            (
                await db.execute(
                    text(
                        "SELECT s.*, t.status, a.expires_at, x.outcome, r.connection_id, "
                        "r.conversation_id, p.message_id FROM career.communication_sends s "
                        "JOIN career.execution_tasks t ON t.id=s.task_id AND t.user_id=s.user_id "
                        "JOIN career.execution_authorizations a ON a.task_id=t.id "
                        "JOIN career.execution_attempts x ON x.task_id=t.id "
                        "JOIN career.execution_resources r ON r.task_id=t.id "
                        "JOIN career.communication_replies p ON p.id=s.reply_id "
                        "WHERE s.reply_id=:reply AND s.user_id=:user"
                    ),
                    {"reply": reply_id, "user": user_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return send_from_row(row) if row else None

    async def get(self, actor: ActorContext, reply_id: UUID) -> CommunicationSend | None:
        try:
            async with self.engine.connect() as db:
                owned = await db.scalar(
                    text(
                        "SELECT 1 FROM career.communication_replies WHERE id=:id AND user_id=:user"
                    ),
                    {"id": reply_id, "user": actor.user_id},
                )
                if not owned:
                    raise CommunicationNotFound("Reply not found")
                return await self._get(db, actor.user_id, reply_id)
        except (DBAPIError, PoolTimeoutError):
            raise CommunicationUnavailable("Send evidence unavailable") from None

    async def resume(self, actor: ActorContext, reply_id: UUID) -> CommunicationSend:
        action = await self.get(actor, reply_id)
        if action is None:
            raise CommunicationNotFound("Send task not found")
        # This only dispatches the same task, never renews or recreates its permission.
        return action

    async def reconcile(
        self, actor: ActorContext, reply_id: UUID, read_task_id: UUID
    ) -> CommunicationSend:
        """Confirm delivery from a later owned read; missing evidence stays unknown."""
        try:
            async with self.engine.begin() as db:
                row = (
                    (
                        await db.execute(
                            text(
                                "SELECT t.id,t.status,x.finished_at,s.source,s.text,"
                                "s.cleanup_required,r.connection_id,r.conversation_id,p.message_id,"
                                "p.read_task_id "
                                "FROM career.communication_sends s "
                                "JOIN career.execution_tasks t ON t.id=s.task_id "
                                "JOIN career.execution_attempts x ON x.task_id=t.id "
                                "JOIN career.execution_resources r ON r.task_id=t.id "
                                "JOIN career.communication_replies p ON p.id=s.reply_id "
                                "WHERE s.reply_id=:reply AND s.user_id=:user FOR UPDATE OF t,x,s"
                            ),
                            {"reply": reply_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise CommunicationNotFound("Send task not found")
                if row["status"] == "completed":
                    result = await self._get(db, actor.user_id, reply_id)
                    assert result is not None
                    return result
                if row["status"] != "unknown" or row["cleanup_required"]:
                    raise CommunicationConflict("Release the uncertain send before reconciling")
                original_page = await db.scalar(
                    text(
                        "SELECT o.page FROM career.execution_read_results o "
                        "JOIN career.execution_tasks t ON t.id=o.task_id "
                        "JOIN career.execution_resources r ON r.task_id=t.id "
                        "WHERE t.id=:read AND t.user_id=:user AND o.user_id=:user "
                        "AND t.kind='boss_read' AND t.status='completed' "
                        "AND r.connection_id=:connection AND r.conversation_id=:conversation "
                        "AND r.connection_version=CAST(:version AS uuid)"
                    ),
                    {
                        "read": row["read_task_id"],
                        "user": actor.user_id,
                        "connection": row["connection_id"],
                        "conversation": row["conversation_id"],
                        "version": row["source"]["connection_version"],
                    },
                )
                if original_page is None:
                    raise CommunicationConflict("Original conversation evidence unavailable")
                original = TypeAdapter(BossPageObservation).validate_python(original_page)
                if (
                    original.state != "ready"
                    or not has_bound_conversation_messages(original)
                    or any(m.conversation_id != row["conversation_id"] for m in original.messages)
                ):
                    raise CommunicationConflict("Original conversation evidence is not verified")
                page_row = (
                    (
                        await db.execute(
                            text(
                                "SELECT p.page FROM career.execution_read_results p "
                                "JOIN career.execution_tasks t ON t.id=p.task_id "
                                "JOIN career.execution_resources r ON r.task_id=t.id "
                                "WHERE t.id=:read AND t.user_id=:user AND p.user_id=:user "
                                "AND t.kind='boss_read' AND t.status='completed' "
                                "AND r.connection_id=:connection "
                                "AND r.conversation_id=:conversation "
                                "AND r.connection_version=CAST(:version AS uuid) "
                                "AND p.observed_at>:finished "
                                "AND p.observed_at>clock_timestamp()-interval '15 minutes'"
                            ),
                            {
                                "read": read_task_id,
                                "user": actor.user_id,
                                "connection": row["connection_id"],
                                "conversation": row["conversation_id"],
                                "finished": row["finished_at"],
                                "version": row["source"]["connection_version"],
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if page_row is None:
                    raise CommunicationConflict("A later completed conversation read is required")
                page = TypeAdapter(BossPageObservation).validate_python(page_row["page"])
                source = [
                    m
                    for m in original.messages
                    if m.message_id == row["message_id"] and m.sender == "recruiter"
                ]
                anchors = [
                    i
                    for i, m in enumerate(page.messages)
                    if m.message_id == row["message_id"]
                    and m.sender == "recruiter"
                    and len(source) == 1
                    and m.content == source[0].content
                ]
                if (
                    page.state != "ready"
                    or not has_bound_conversation_messages(page)
                    or len(anchors) != 1
                    or any(m.conversation_id != row["conversation_id"] for m in page.messages)
                ):
                    raise CommunicationConflict("Original recruiter message is not verified")
                before = {m.message_id for m in original.messages}
                matches = [
                    m
                    for m in page.messages[anchors[0] + 1 :]
                    if m.message_id not in before
                    and m.sender == "candidate"
                    and m.content == " ".join(row["text"].split())
                ]
                if len(matches) != 1:
                    raise CommunicationConflict("Delivery remains unknown; do not send again")
                params = {"task": row["id"], "message": matches[0].message_id}
                await db.execute(
                    text(
                        "UPDATE career.execution_tasks SET status='completed',"
                        "updated_at=clock_timestamp() WHERE id=:task"
                    ),
                    params,
                )
                await db.execute(
                    text(
                        "UPDATE career.execution_attempts SET status='completed',"
                        "outcome='send_completed',updated_at=clock_timestamp() WHERE task_id=:task"
                    ),
                    params,
                )
                await db.execute(
                    text(
                        "UPDATE career.communication_sends SET evidence_message_id=:message "
                        "WHERE task_id=:task"
                    ),
                    params,
                )
                result = await self._get(db, actor.user_id, reply_id)
                assert result is not None
                return result
        except (DBAPIError, PoolTimeoutError):
            raise CommunicationUnavailable("Send reconciliation unavailable") from None

    async def cancel(self, actor: ActorContext, reply_id: UUID) -> CommunicationSend:
        try:
            async with self.engine.begin() as db:
                row = (
                    (
                        await db.execute(
                            text(
                                "SELECT t.id,t.status FROM career.execution_tasks t "
                                "JOIN career.communication_sends s ON s.task_id=t.id "
                                "WHERE s.reply_id=:reply AND s.user_id=:user FOR UPDATE OF t"
                            ),
                            {"reply": reply_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise CommunicationNotFound("Send task not found")
                if row["status"] != "cancelled":
                    if row["status"] != "accepted":
                        raise CommunicationConflict(
                            "A started send cannot be cancelled or replayed"
                        )
                    await db.execute(
                        text(
                            "UPDATE career.execution_tasks SET status='cancelled',"
                            "updated_at=clock_timestamp() WHERE id=:task"
                        ),
                        {"task": row["id"]},
                    )
                    await db.execute(
                        text(
                            "UPDATE career.execution_attempts SET status='cancelled',"
                            "outcome='cancelled_before_start',finished_at=clock_timestamp() "
                            "WHERE task_id=:task"
                        ),
                        {"task": row["id"]},
                    )
                    await db.execute(
                        text(
                            "UPDATE career.execution_authorizations SET status='revoked',"
                            "revoked_at=clock_timestamp() WHERE task_id=:task"
                        ),
                        {"task": row["id"]},
                    )
                result = await self._get(db, actor.user_id, reply_id)
                assert result is not None
                return result
        except (DBAPIError, PoolTimeoutError):
            raise CommunicationUnavailable("Send cancellation unavailable") from None

    async def accept(
        self,
        actor: ActorContext,
        reply_id: UUID,
        version: UUID,
        request_key: UUID,
        *,
        automation_id: UUID | None = None,
    ) -> CommunicationSend:
        try:
            request_id = UUID(actor.request_id)
        except ValueError:
            raise CommunicationConflict("Invalid action request") from None
        try:
            async with self.engine.begin() as db:
                await db.execute(
                    text('SELECT id FROM auth."user" WHERE id=:id FOR UPDATE'),
                    {"id": actor.user_id},
                )
                delegation = None
                if automation_id is not None:
                    delegation = (
                        (
                            await db.execute(
                                text(
                                    "SELECT * FROM career.recruiting_automations WHERE id=:id "
                                    "AND user_id=:user FOR UPDATE"
                                ),
                                {"id": automation_id, "user": actor.user_id},
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if delegation is None or delegation["reply_id"] != reply_id:
                        raise CommunicationConflict("Reply delegation is inactive or exhausted")
                connection = (
                    (
                        await db.execute(
                            text(
                                "SELECT c.* FROM career.boss_connections c "
                                "JOIN career.communication_replies r ON r.connection_id=c.id "
                                "AND r.user_id=c.user_id WHERE r.id=:reply AND r.user_id=:user "
                                "FOR UPDATE OF c"
                            ),
                            {"reply": reply_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if connection is None:
                    raise CommunicationNotFound("Reply not found")
                row = (
                    (
                        await db.execute(
                            text(
                                "SELECT * FROM career.communication_replies WHERE id=:id AND "
                                "user_id=:user "
                                "FOR UPDATE"
                            ),
                            {"id": reply_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one()
                )
                replay = await self._get(db, actor.user_id, reply_id)
                if replay is not None:
                    key = await db.scalar(
                        text("SELECT request_key FROM career.execution_tasks WHERE id=:id"),
                        {"id": replay.id},
                    )
                    bound_version = await db.scalar(
                        text(
                            "SELECT reply_version FROM career.communication_sends WHERE task_id=:id"
                        ),
                        {"id": replay.id},
                    )
                    bound_automation = await db.scalar(
                        text(
                            "SELECT automation_id FROM career.communication_sends WHERE task_id=:id"
                        ),
                        {"id": replay.id},
                    )
                    if (
                        key != request_key
                        or bound_version != version
                        or bound_automation != automation_id
                    ):
                        raise CommunicationConflict("This source already has a send attempt")
                    return replay
                reply = reply_from_row(row)
                if delegation is not None and (
                    delegation["connection_id"] != reply.connection_id
                    or delegation["conversation_ids"][delegation["position"]]
                    != reply.conversation_id
                    or delegation["connection_version"] != connection["version"]
                ):
                    raise CommunicationConflict("Reply is outside the delegated scope")
                now = cast(datetime, await db.scalar(text("SELECT clock_timestamp()")))
                if delegation is not None and (
                    delegation["status"] != "running"
                    or delegation["stage"] != "send"
                    or not delegation["in_flight"]
                    or delegation["expires_at"] <= now
                    or delegation["sends_reserved"] >= delegation["max_sends"]
                ):
                    raise CommunicationConflict("Reply delegation is inactive or exhausted")
                if (
                    reply.version != version
                    or reply.status != "waiting"
                    or reply.decision is None
                    or not is_factual_reply(reply.decision, row["source"]["profile_facts"])
                    or not reply.decision.text.strip()
                    or reply.expires_at <= now
                    or connection["status"] != "connected"
                    or str(connection["version"]) != row["source"]["connection_version"]
                ):
                    raise CommunicationConflict("Read a fresh factual reply before authorizing")
                # Career facts/rules used in the immutable draft must still be confirmed.
                profile_version = await db.scalar(
                    text("SELECT version::text FROM career.profiles WHERE user_id=:user FOR SHARE"),
                    {"user": actor.user_id},
                )
                rules = (
                    (
                        await db.execute(
                            text(
                                "SELECT id::text,version::text FROM career.workspace_memories "
                                "WHERE user_id=:user AND kind='rule' AND state='confirmed' "
                                "AND project_id IS NULL ORDER BY id FOR SHARE"
                            ),
                            {"user": actor.user_id},
                        )
                    )
                    .mappings()
                    .all()
                )
                if (
                    profile_version != row["source"]["profile_version"]
                    or [dict(r) for r in rules] != row["source"]["rules"]
                ):
                    raise CommunicationConflict("Confirmed career context changed")
                occupied = await db.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM career.execution_resources r "
                        "JOIN career.execution_tasks t ON t.id=r.task_id "
                        "WHERE r.connection_id=:connection AND r.user_id=:user "
                        "AND t.status IN ('accepted','running','waiting','unknown')) "
                        "OR EXISTS (SELECT 1 FROM career.boss_saved_login_viewers "
                        "WHERE connection_id=:connection AND user_id=:user "
                        "AND status IN ('starting','live','closing')) "
                        "OR EXISTS (SELECT 1 FROM career.communication_sends s "
                        "JOIN career.execution_resources r ON r.task_id=s.task_id "
                        "WHERE r.connection_id=:connection AND s.cleanup_required)"
                    ),
                    {"connection": reply.connection_id, "user": actor.user_id},
                )
                if occupied:
                    raise CommunicationConflict("Finish the active browser task before sending")
                task, authorization, attempt = uuid4(), uuid4(), uuid4()
                params = {
                    "task": task,
                    "user": actor.user_id,
                    "key": request_key,
                    "authorization": authorization,
                    "attempt": attempt,
                    "request": request_id,
                    "reply": reply_id,
                    "version": version,
                    "text": reply.decision.text,
                    "source": json.dumps(row["source"], ensure_ascii=False),
                    "connection": reply.connection_id,
                    "connection_version": connection["version"],
                    "conversation": reply.conversation_id,
                }
                await db.execute(
                    text(
                        "INSERT INTO career.execution_tasks (id,user_id,kind,request_key) "
                        "VALUES (:task,:user,'boss_reply',:key)"
                    ),
                    params,
                )
                await db.execute(
                    text(
                        "INSERT INTO career.execution_authorizations "
                        "(id,task_id,user_id,scope,expires_at) VALUES "
                        "(:authorization,:task,:user,'boss.reply',clock_timestamp()+interval "
                        "'5 minutes')"
                    ),
                    params,
                )
                await db.execute(
                    text(
                        "INSERT INTO career.execution_attempts "
                        "(id,task_id,authorization_id,user_id,request_id) VALUES "
                        "(:attempt,:task,:authorization,:user,:request)"
                    ),
                    params,
                )
                await db.execute(
                    text(
                        "INSERT INTO career.execution_resources "
                        "(task_id,user_id,kind,connection_id,connection_version,"
                        "conversation_id) VALUES "
                        "(:task,:user,'boss_connection',:connection,:connection_version,:conversation)"
                    ),
                    params,
                )
                await db.execute(
                    text(
                        "INSERT INTO career.communication_sends "
                        "(task_id,user_id,reply_id,reply_version,text,source,automation_id) "
                        "VALUES (:task,:user,:reply,:version,:text,"
                        "CAST(:source AS jsonb),:automation)"
                    ),
                    params | {"automation": automation_id},
                )
                if automation_id is not None:
                    await db.execute(
                        text(
                            "UPDATE career.recruiting_automations "
                            "SET sends_reserved=sends_reserved+1,"
                            "send_task_id=:task WHERE id=:id"
                        ),
                        {"id": automation_id, "task": task},
                    )
                result = await self._get(db, actor.user_id, reply_id)
                assert result is not None
                return result
        except IntegrityError:
            raise CommunicationConflict("Send request already exists") from None
        except (DBAPIError, PoolTimeoutError):
            raise CommunicationUnavailable("Send authorization unavailable") from None

    async def claim(self, task_id: UUID) -> SendClaim | None:
        try:
            async with self.engine.begin() as db:
                delegated = await db.scalar(
                    text(
                        "SELECT automation_id FROM career.communication_sends WHERE task_id=:task"
                    ),
                    {"task": task_id},
                )
                if delegated is not None:
                    active = await db.scalar(
                        text(
                            "SELECT 1 FROM career.recruiting_automations WHERE id=:id "
                            "AND status='running' AND expires_at>clock_timestamp() FOR SHARE"
                        ),
                        {"id": delegated},
                    )
                    if not active:
                        await self._finish(db, task_id, SendEvidence("failed"))
                        return None
                await db.execute(
                    text(
                        "SELECT c.id FROM career.boss_connections c JOIN "
                        "career.execution_resources r "
                        "ON r.connection_id=c.id AND r.user_id=c.user_id WHERE r.task_id=:task "
                        "FOR SHARE OF c"
                    ),
                    {"task": task_id},
                )
                row = (
                    (
                        await db.execute(
                            text(
                                "SELECT t.status,t.user_id,a.id AS authorization,a.status AS "
                                "authorized,"
                                "a.expires_at,x.id AS "
                                "attempt,x.request_id,r.conversation_id,c.status AS connected,"
                                "c.version=r.connection_version AS "
                                "current_connection,s.text,s.source,p.message_id "
                                ",p.expires_at AS source_expires,p.status AS reply_status,"
                                "p.decision "
                                "FROM career.execution_tasks t JOIN "
                                "career.execution_authorizations a "
                                "ON a.task_id=t.id JOIN career.execution_attempts x ON "
                                "x.task_id=t.id "
                                "JOIN career.execution_resources r ON r.task_id=t.id "
                                "JOIN career.boss_connections c ON c.id=r.connection_id AND "
                                "c.user_id=t.user_id "
                                "JOIN career.communication_sends s ON s.task_id=t.id "
                                "JOIN career.communication_replies p ON p.id=s.reply_id "
                                "WHERE t.id=:task AND t.kind='boss_reply' FOR UPDATE OF t,a,x"
                            ),
                            {"task": task_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None or row["status"] != "accepted":
                    return None
                profile_version = await db.scalar(
                    text("SELECT version::text FROM career.profiles WHERE user_id=:user FOR SHARE"),
                    {"user": row["user_id"]},
                )
                rules = (
                    (
                        await db.execute(
                            text(
                                "SELECT id::text,version::text FROM career.workspace_memories "
                                "WHERE user_id=:user AND kind='rule' AND state='confirmed' "
                                "AND project_id IS NULL ORDER BY id FOR SHARE"
                            ),
                            {"user": row["user_id"]},
                        )
                    )
                    .mappings()
                    .all()
                )
                now = cast(datetime, await db.scalar(text("SELECT clock_timestamp()")))
                if (
                    row["authorized"] != "active"
                    or row["expires_at"] <= now
                    or row["connected"] != "connected"
                    or not row["current_connection"]
                    or row["source_expires"] <= now
                    or row["reply_status"] != "waiting"
                    or row["decision"] is None
                    or row["decision"].get("category") != "routine"
                    or row["decision"].get("text") != row["text"]
                    or not is_factual_reply(
                        TypeAdapter(ReplyDecision).validate_python(row["decision"]),
                        row["source"]["profile_facts"],
                    )
                    or profile_version != row["source"]["profile_version"]
                    or [dict(r) for r in rules] != row["source"]["rules"]
                ):
                    await self._finish(db, task_id, SendEvidence("failed"))
                    return None
                session = uuid4()
                await db.execute(
                    text(
                        "UPDATE career.execution_tasks SET "
                        "status='running',updated_at=clock_timestamp() "
                        "WHERE id=:task"
                    ),
                    {"task": task_id},
                )
                await db.execute(
                    text(
                        "UPDATE career.execution_attempts SET "
                        "status='running',outcome='send_preparing',"
                        "browser_session_id=:session,started_at=clock_timestamp(),"
                        "updated_at=clock_timestamp() WHERE task_id=:task"
                    ),
                    {"task": task_id, "session": session},
                )
                context = BrowserControlContext(
                    row["user_id"],
                    session,
                    task_id,
                    row["authorization"],
                    row["expires_at"],
                    row["attempt"],
                    row["request_id"],
                    "boss-reply",
                    row["conversation_id"],
                )
                messages = row["source"]["payload"]["messages"]
                human = [m for m in messages if m["sender"] in {"candidate", "recruiter"}]
                return SendClaim(context, row["message_id"], human[-1]["content"], row["text"])
        except (DBAPIError, PoolTimeoutError):
            raise CommunicationUnavailable("Send claim unavailable") from None

    async def _finish(self, db: AsyncConnection, task_id: UUID, evidence: SendEvidence) -> None:
        if evidence.state not in {"completed", "failed", "unknown"} or (
            evidence.state == "completed" and not evidence.message_id
        ):
            raise CommunicationConflict("Send completion requires message evidence")
        params = {
            "task": task_id,
            "state": evidence.state,
            "outcome": "send_" + evidence.state,
            "message": evidence.message_id,
            "cleanup": evidence.cleanup_required,
        }
        changed = await db.scalar(
            text(
                "UPDATE career.execution_tasks SET status=:state,updated_at=clock_timestamp() "
                "WHERE id=:task AND kind='boss_reply' AND status IN ('accepted','running') "
                "RETURNING id"
            ),
            params,
        )
        if not changed:
            # Cleanup may complete after delivery was already evidenced. Never rewrite delivery.
            await db.execute(
                text(
                    "UPDATE career.communication_sends SET cleanup_required=:cleanup "
                    "WHERE task_id=:task AND cleanup_required AND :cleanup=false"
                ),
                params,
            )
            return
        await db.execute(
            text(
                "UPDATE career.execution_attempts SET status=:state,outcome=:outcome,"
                "finished_at=clock_timestamp(),updated_at=clock_timestamp() WHERE task_id=:task"
            ),
            params,
        )
        await db.execute(
            text(
                "UPDATE career.execution_authorizations SET "
                "status='revoked',revoked_at=clock_timestamp() "
                "WHERE task_id=:task"
            ),
            params,
        )
        await db.execute(
            text(
                "UPDATE career.communication_sends SET evidence_message_id=:message,"
                "cleanup_required=:cleanup WHERE task_id=:task"
            ),
            params,
        )

    async def finish(self, task_id: UUID, evidence: SendEvidence) -> None:
        try:
            async with self.engine.begin() as db:
                await self._finish(db, task_id, evidence)
        except (DBAPIError, PoolTimeoutError):
            raise CommunicationUnavailable("Send evidence persistence unconfirmed") from None
