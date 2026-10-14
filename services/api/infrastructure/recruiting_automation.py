import json
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.application.context import ActorContext
from services.api.application.ports.recruiting_automation import AutomationStep
from services.api.domain.communication import (
    CommunicationConflict,
    CommunicationNotFound,
    CommunicationUnavailable,
)
from services.api.domain.recruiting_automation import (
    AutomationStatus,
    RecruitingAutomation,
    validate_automation_scope,
)


def automation_from_row(row: RowMapping) -> RecruitingAutomation:
    return RecruitingAutomation(
        row["id"],
        row["connection_id"],
        row["version"],
        cast(AutomationStatus, row["status"]),
        tuple(row["conversation_ids"]),
        row["expires_at"],
        row["max_sends"],
        row["sends_reserved"],
        row["interval_seconds"],
        row["outcome"],
        row["read_task_id"],
        row["reply_id"],
        row["send_task_id"],
    )


class PostgresAutomationRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def accept(
        self,
        actor: ActorContext,
        connection: UUID,
        version: UUID,
        key: UUID,
        conversations: tuple[str, ...],
        max_sends: int,
        duration_minutes: int,
        interval_seconds: int,
    ) -> RecruitingAutomation:
        validate_automation_scope(conversations, max_sends)
        if not 1 <= duration_minutes <= 480 or not 300 <= interval_seconds <= 3600:
            raise CommunicationConflict("Delegation duration or interval exceeds its limit")
        try:
            async with self.engine.begin() as db:
                await db.execute(
                    text('SELECT id FROM auth."user" WHERE id=:user FOR UPDATE'),
                    {"user": actor.user_id},
                )
                owned = (
                    (
                        await db.execute(
                            text(
                                "SELECT status,version FROM career.boss_connections WHERE id=:id "
                                "AND user_id=:user FOR UPDATE"
                            ),
                            {"id": connection, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if owned is None:
                    raise CommunicationNotFound("Recruiting connection not found")
                existing = (
                    (
                        await db.execute(
                            text(
                                "SELECT * FROM career.recruiting_automations WHERE user_id=:user "
                                "AND request_key=:key"
                            ),
                            {"user": actor.user_id, "key": key},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing is not None:
                    if (
                        existing["connection_id"] != connection
                        or existing["connection_version"] != version
                        or tuple(existing["conversation_ids"]) != conversations
                        or existing["max_sends"] != max_sends
                        or existing["duration_minutes"] != duration_minutes
                        or existing["interval_seconds"] != interval_seconds
                    ):
                        raise CommunicationConflict("Delegation request key changed scope")
                    return automation_from_row(existing)
                if owned["status"] != "connected" or owned["version"] != version:
                    raise CommunicationConflict("Read the current connected account first")
                verified = await db.scalar(
                    text(
                        "SELECT p.page FROM career.execution_read_results p "
                        "JOIN career.execution_resources r ON r.task_id=p.task_id "
                        "JOIN career.execution_tasks t ON t.id=p.task_id "
                        "WHERE t.user_id=:user AND t.status='completed' "
                        "AND r.connection_id=:connection AND r.connection_version=:version "
                        "AND p.observed_at>clock_timestamp()-interval '15 minutes' "
                        "AND p.page->>'state'='ready' ORDER BY p.observed_at DESC LIMIT 1"
                    ),
                    {"user": actor.user_id, "connection": connection, "version": version},
                )
                known = (
                    {c["conversation_id"] for c in verified["conversations"]} if verified else set()
                )
                if not set(conversations) <= known:
                    raise CommunicationConflict("Select conversations from a recent verified read")
                row = (
                    (
                        await db.execute(
                            text(
                                "INSERT INTO career.recruiting_automations "
                                "(id,user_id,connection_id,connection_version,version,request_key,"
                                "conversation_ids,expires_at,max_sends,"
                                "interval_seconds,duration_minutes) VALUES "
                                "(:id,:user,:connection,:version,:revision,:key,"
                                "CAST(:scope AS jsonb),clock_timestamp()+"
                                "make_interval(mins=>:duration),:max,:interval,:duration) "
                                "RETURNING *"
                            ),
                            {
                                "id": uuid4(),
                                "user": actor.user_id,
                                "connection": connection,
                                "version": version,
                                "revision": uuid4(),
                                "key": key,
                                "scope": json.dumps(conversations),
                                "duration": duration_minutes,
                                "max": max_sends,
                                "interval": interval_seconds,
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                return automation_from_row(row)
        except IntegrityError:
            raise CommunicationConflict("An active delegation already exists") from None
        except DBAPIError:
            raise CommunicationUnavailable("Delegation storage unavailable") from None

    async def latest(self, actor: ActorContext, connection: UUID) -> RecruitingAutomation | None:
        async with self.engine.connect() as db:
            owned = await db.scalar(
                text("SELECT 1 FROM career.boss_connections WHERE id=:id AND user_id=:user"),
                {"id": connection, "user": actor.user_id},
            )
            if not owned:
                raise CommunicationNotFound("Recruiting connection not found")
            row = (
                (
                    await db.execute(
                        text(
                            "SELECT * FROM career.recruiting_automations WHERE user_id=:user "
                            "AND connection_id=:connection ORDER BY created_at DESC LIMIT 1"
                        ),
                        {"user": actor.user_id, "connection": connection},
                    )
                )
                .mappings()
                .one_or_none()
            )
            return automation_from_row(row) if row else None

    async def get(self, actor: ActorContext, reference: UUID) -> RecruitingAutomation:
        async with self.engine.connect() as db:
            row = (
                (
                    await db.execute(
                        text(
                            "SELECT * FROM career.recruiting_automations "
                            "WHERE id=:id AND user_id=:user"
                        ),
                        {"id": reference, "user": actor.user_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise CommunicationNotFound("Delegation not found")
            return automation_from_row(row)

    async def stop(
        self, actor: ActorContext, reference: UUID, version: UUID
    ) -> RecruitingAutomation:
        async with self.engine.begin() as db:
            row = (
                (
                    await db.execute(
                        text(
                            "SELECT * FROM career.recruiting_automations "
                            "WHERE id=:id AND user_id=:user FOR UPDATE"
                        ),
                        {"id": reference, "user": actor.user_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise CommunicationNotFound("Delegation not found")
            if row["version"] != version:
                raise CommunicationConflict("Delegation version changed")
            if row["status"] not in {"completed", "cancelled", "timed_out"}:
                await db.execute(
                    text(
                        "UPDATE career.recruiting_automations SET status='waiting',"
                        "outcome='stopped',updated_at=clock_timestamp() WHERE id=:id"
                    ),
                    {"id": reference},
                )
        return await self.get(actor, reference)

    async def confirm_stop(self, actor: ActorContext, reference: UUID) -> RecruitingAutomation:
        async with self.engine.begin() as db:
            await db.execute(
                text(
                    "UPDATE career.recruiting_automations SET status='cancelled',"
                    "updated_at=clock_timestamp() WHERE id=:id AND user_id=:user "
                    "AND status='waiting' AND outcome='stopped'"
                ),
                {"id": reference, "user": actor.user_id},
            )
        return await self.get(actor, reference)

    async def claim(self, reference: UUID) -> AutomationStep | None:
        async with self.engine.begin() as db:
            row = (
                (
                    await db.execute(
                        text(
                            "SELECT a.*,c.status AS connected,c.version AS current_version,"
                            "a.expires_at>clock_timestamp() AS alive "
                            "FROM career.recruiting_automations a "
                            "JOIN career.boss_connections c "
                            "ON c.id=a.connection_id AND c.user_id=a.user_id "
                            "WHERE a.id=:id FOR UPDATE OF a"
                        ),
                        {"id": reference},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None or row["status"] not in {"accepted", "running"}:
                return None
            outcome = None
            status = "waiting"
            if not row["alive"]:
                status, outcome = "timed_out", "expired"
            elif (
                row["connected"] != "connected"
                or row["current_version"] != row["connection_version"]
            ):
                outcome = "connection_changed"
            elif row["in_flight"]:
                # Lost activity cannot repeat read navigation or any external write.
                outcome = "interrupted_step_requires_review"
            elif row["sends_reserved"] >= row["max_sends"]:
                status, outcome = "completed", "limit_reached"
            if outcome:
                await db.execute(
                    text(
                        "UPDATE career.recruiting_automations SET status=:status,outcome=:outcome "
                        "WHERE id=:id"
                    ),
                    {"id": reference, "status": status, "outcome": outcome},
                )
                return None
            await db.execute(
                text(
                    "UPDATE career.recruiting_automations SET status='running',in_flight=true,"
                    "updated_at=clock_timestamp() WHERE id=:id"
                ),
                {"id": reference},
            )
            return AutomationStep(
                ActorContext(row["user_id"], str(uuid4())),
                automation_from_row(row),
                row["connection_version"],
                row["conversation_ids"][row["position"]],
                row["stage"],
            )

    async def decision_for_message(self, step: AutomationStep, message_id: str) -> UUID | None:
        async with self.engine.connect() as db:
            return cast(
                UUID | None,
                await db.scalar(
                    text(
                        "SELECT id FROM career.communication_replies "
                        "WHERE user_id=:user "
                        "AND connection_id=:connection AND conversation_id=:conversation "
                        "AND message_id=:message AND (EXISTS "
                        "(SELECT 1 FROM career.communication_sends s "
                        "WHERE s.reply_id=career.communication_replies.id) OR NOT "
                        "(status IN ('accepted','running','waiting','timed_out') "
                        "AND expires_at<=clock_timestamp())) "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {
                        "user": step.actor.user_id,
                        "connection": step.automation.connection_id,
                        "conversation": step.conversation_id,
                        "message": message_id,
                    },
                ),
            )

    async def finish(
        self,
        reference: UUID,
        *,
        stage: str | None = None,
        outcome: str | None = None,
        advance: bool = False,
        read: UUID | None = None,
        reply: UUID | None = None,
        checkpoint: bool = False,
    ) -> int:
        async with self.engine.begin() as db:
            row = (
                (
                    await db.execute(
                        text("SELECT * FROM career.recruiting_automations WHERE id=:id FOR UPDATE"),
                        {"id": reference},
                    )
                )
                .mappings()
                .one()
            )
            if row["status"] not in {"accepted", "running"}:
                if checkpoint:
                    # Stop can win between child acceptance and this checkpoint.
                    # Preserve its identity so halt can revoke the queued child.
                    await db.execute(
                        text(
                            "UPDATE career.recruiting_automations "
                            "SET read_task_id=COALESCE(:read,read_task_id),"
                            "reply_id=COALESCE(:reply,reply_id) WHERE id=:id"
                        ),
                        {"id": reference, "read": read, "reply": reply},
                    )
                return 0
            position = (
                (row["position"] + 1) % len(row["conversation_ids"]) if advance else row["position"]
            )
            remaining = await db.scalar(
                text("SELECT GREATEST(1,CEIL(EXTRACT(EPOCH FROM :expires-clock_timestamp())))"),
                {"expires": row["expires_at"]},
            )
            delay = min(row["interval_seconds"] if advance and position == 0 else 1, int(remaining))
            completed = advance and row["sends_reserved"] >= row["max_sends"]
            await db.execute(
                text(
                    "UPDATE career.recruiting_automations SET in_flight=:checkpoint,stage=:stage,"
                    "position=:position,status=:status,outcome=:outcome,"
                    "read_task_id=COALESCE(:read,read_task_id),reply_id=COALESCE(:reply,reply_id),"
                    "updated_at=clock_timestamp() WHERE id=:id"
                ),
                {
                    "id": reference,
                    "stage": stage or row["stage"],
                    "position": position,
                    "status": "waiting" if outcome else "completed" if completed else "running",
                    "outcome": outcome or ("limit_reached" if completed else None),
                    "read": read,
                    "reply": reply,
                    "checkpoint": checkpoint,
                },
            )
            return 0 if outcome or completed else delay

    async def halt(self, reference: UUID) -> RecruitingAutomation | None:
        async with self.engine.begin() as db:
            row = (
                (
                    await db.execute(
                        text(
                            "UPDATE career.recruiting_automations "
                            "SET status=CASE WHEN status IN ('accepted','running') "
                            "THEN 'waiting' ELSE status END,"
                            "outcome=CASE WHEN status IN ('accepted','running') "
                            "THEN 'interrupted_step_requires_review' ELSE outcome END,"
                            "updated_at=clock_timestamp() WHERE id=:id RETURNING *"
                        ),
                        {"id": reference},
                    )
                )
                .mappings()
                .one_or_none()
            )
            return automation_from_row(row) if row else None
