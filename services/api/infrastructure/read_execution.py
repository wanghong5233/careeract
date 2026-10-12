import json
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from services.api.application.context import ActorContext
from services.api.application.ports.boss_page import BossPageObservation
from services.api.application.ports.browser_control import BrowserControlContext
from services.api.application.ports.read_execution import ReadPageResult
from services.api.domain.execution import (
    BossReadTarget,
    ExecutionConflict,
    ExecutionUnavailable,
    MaterialReadTarget,
    ReadExecution,
    ReadTarget,
)
from services.api.infrastructure.execution import (
    attempt_from_row,
    authorization_from_row,
    task_from_row,
)


def target_from_row(row: RowMapping) -> ReadTarget:
    if row["kind"] == "boss_connection":
        return BossReadTarget(
            row["connection_id"], row["connection_version"], row["conversation_id"]
        )
    if row["kind"] == "material_version":
        return MaterialReadTarget(
            row["material_id"], row["material_version_id"], row["material_version"]
        )
    raise ExecutionUnavailable("Execution resource is invalid")


def read_kind(target: ReadTarget) -> tuple[str, str]:
    if isinstance(target, BossReadTarget):
        return "boss_read", "boss.read"
    if isinstance(target, MaterialReadTarget):
        return "material_read", "material.read"
    raise ExecutionConflict("Unsupported read resource")


class PostgresReadExecutionRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    @staticmethod
    async def _read(
        database: AsyncConnection, actor: ActorContext, task_id: UUID, *, lock: bool = False
    ) -> ReadExecution | None:
        parameters = {"task": task_id, "user": actor.user_id}
        task = (
            (
                await database.execute(
                    text(
                        "SELECT * FROM career.execution_tasks WHERE id=:task AND user_id=:user "
                        "AND kind IN ('boss_read','material_read')"
                        + (" FOR UPDATE" if lock else "")
                    ),
                    parameters,
                )
            )
            .mappings()
            .one_or_none()
        )
        if task is None:
            return None
        authorization = (
            (
                await database.execute(
                    text(
                        "SELECT * FROM career.execution_authorizations "
                        "WHERE task_id=:task AND user_id=:user" + (" FOR UPDATE" if lock else "")
                    ),
                    parameters,
                )
            )
            .mappings()
            .one()
        )
        attempt = (
            (
                await database.execute(
                    text(
                        "SELECT * FROM career.execution_attempts "
                        "WHERE task_id=:task AND user_id=:user" + (" FOR UPDATE" if lock else "")
                    ),
                    parameters,
                )
            )
            .mappings()
            .one()
        )
        resource = (
            (
                await database.execute(
                    text(
                        "SELECT * FROM career.execution_resources "
                        "WHERE task_id=:task AND user_id=:user"
                    ),
                    parameters,
                )
            )
            .mappings()
            .one()
        )
        target = target_from_row(resource)
        kind, scope = read_kind(target)
        if task["kind"] != kind or authorization["scope"] != scope:
            raise ExecutionUnavailable("Execution resource does not match its authorization")
        return ReadExecution(
            task_from_row(task),
            authorization_from_row(authorization),
            attempt_from_row(attempt),
            target,
        )

    async def read(self, actor: ActorContext, task_id: UUID) -> ReadExecution | None:
        try:
            async with self.engine.begin() as database:
                await database.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                return await self._read(database, actor, task_id)
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Read execution storage is unavailable") from None

    async def accept(
        self,
        actor: ActorContext,
        *,
        target: ReadTarget,
        request_key: UUID,
        authorization_lifetime: timedelta,
    ) -> ReadExecution:
        kind, scope = read_kind(target)
        try:
            request_id = UUID(actor.request_id)
        except ValueError:
            raise ExecutionConflict("Read request context is invalid") from None
        try:
            async with self.engine.begin() as database:
                owner = await database.scalar(
                    text('SELECT id FROM auth."user" WHERE id=:user FOR UPDATE'),
                    {"user": actor.user_id},
                )
                if owner is None:
                    raise ExecutionConflict("Read execution owner is unavailable")
                existing = await database.scalar(
                    text(
                        "SELECT id FROM career.execution_tasks "
                        "WHERE user_id=:user AND request_key=:key"
                    ),
                    {"user": actor.user_id, "key": request_key},
                )
                if existing is not None:
                    current = await self._read(database, actor, existing)
                    if current is None or current.target != target or current.task.kind != kind:
                        raise ExecutionConflict("Read request key has different content")
                    return current
                now = cast(datetime, await database.scalar(text("SELECT clock_timestamp()")))
                if not 0 < authorization_lifetime.total_seconds() <= 15 * 60:
                    raise ExecutionConflict("Read authorization must expire within 15 minutes")
                authorization_expires_at = now + authorization_lifetime
                await self._validate_target(database, actor, target)
                task_id, authorization_id = uuid4(), uuid4()
                parameters = {
                    "task": task_id,
                    "user": actor.user_id,
                    "kind": kind,
                    "key": request_key,
                    "authorization": authorization_id,
                    "scope": scope,
                    "expires": authorization_expires_at,
                    "attempt": uuid4(),
                    "request": request_id,
                }
                await database.execute(
                    text(
                        "INSERT INTO career.execution_tasks (id,user_id,kind,request_key) "
                        "VALUES (:task,:user,:kind,:key)"
                    ),
                    parameters,
                )
                await database.execute(
                    text(
                        "INSERT INTO career.execution_authorizations "
                        "(id,task_id,user_id,scope,expires_at) "
                        "VALUES (:authorization,:task,:user,:scope,:expires)"
                    ),
                    parameters,
                )
                await database.execute(
                    text(
                        "INSERT INTO career.execution_attempts "
                        "(id,task_id,authorization_id,user_id,request_id) "
                        "VALUES (:attempt,:task,:authorization,:user,:request)"
                    ),
                    parameters,
                )
                await database.execute(
                    text(
                        "INSERT INTO career.execution_resources "
                        "(task_id,user_id,kind,connection_id,connection_version,material_id,"
                        "material_version_id,material_version,conversation_id) "
                        "VALUES (:task,:user,:resource_kind,:connection,:connection_version,"
                        ":material,:material_version_id,:material_version,:conversation_id)"
                    ),
                    {
                        "task": task_id,
                        "user": actor.user_id,
                        "resource_kind": "boss_connection"
                        if isinstance(target, BossReadTarget)
                        else "material_version",
                        "connection": target.connection_id
                        if isinstance(target, BossReadTarget)
                        else None,
                        "connection_version": target.connection_version
                        if isinstance(target, BossReadTarget)
                        else None,
                        "material": target.material_id
                        if isinstance(target, MaterialReadTarget)
                        else None,
                        "material_version_id": target.version_id
                        if isinstance(target, MaterialReadTarget)
                        else None,
                        "material_version": target.material_version
                        if isinstance(target, MaterialReadTarget)
                        else None,
                        "conversation_id": target.conversation_id
                        if isinstance(target, BossReadTarget)
                        else None,
                    },
                )
                result = await self._read(database, actor, task_id)
                assert result is not None
                return result
        except IntegrityError:
            raise ExecutionConflict("Read execution could not be accepted") from None
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Read execution storage is unavailable") from None

    @staticmethod
    async def _validate_target(
        database: AsyncConnection, actor: ActorContext, target: ReadTarget
    ) -> None:
        if isinstance(target, BossReadTarget):
            resource = (
                (
                    await database.execute(
                        text(
                            "SELECT status,version FROM career.boss_connections "
                            "WHERE id=:id AND user_id=:user FOR UPDATE"
                        ),
                        {"id": target.connection_id, "user": actor.user_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                resource is None
                or resource["status"] != "connected"
                or resource["version"] != target.connection_version
            ):
                raise ExecutionConflict("Read connection is unavailable or has changed")
        else:
            resource = (
                (
                    await database.execute(
                        text(
                            "SELECT state,version,current_version_id FROM career.materials "
                            "WHERE id=:id AND user_id=:user FOR UPDATE"
                        ),
                        {"id": target.material_id, "user": actor.user_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                resource is None
                or resource["state"] != "active"
                or resource["version"] != target.material_version
                or resource["current_version_id"] != target.version_id
            ):
                raise ExecutionConflict("Read material is unavailable or has changed")

    async def cancel(self, actor: ActorContext, task_id: UUID) -> ReadExecution:
        try:
            async with self.engine.begin() as database:
                current = await self._read(database, actor, task_id, lock=True)
                if current is None:
                    raise ExecutionConflict("Read execution is unavailable")
                if current.task.status == "cancelled":
                    return current
                stopping = (
                    current.task.status == "waiting"
                    and current.attempt.outcome == "read_stop_requested"
                )
                if stopping:
                    return current
                if current.task.status not in {"accepted", "running"}:
                    raise ExecutionConflict("Started read execution requires reconciliation")
                started = current.attempt.browser_session_id is not None
                parameters = {"task": task_id, "user": actor.user_id}
                parameters.update(
                    status="waiting" if started else "cancelled",
                    outcome="read_stop_requested" if started else "cancelled_before_start",
                )
                await database.execute(
                    text(
                        "UPDATE career.execution_authorizations SET status='revoked', "
                        "revoked_at=clock_timestamp() WHERE task_id=:task AND user_id=:user"
                    ),
                    parameters,
                )
                await database.execute(
                    text(
                        "UPDATE career.execution_tasks SET status=:status, "
                        "updated_at=clock_timestamp() WHERE id=:task AND user_id=:user"
                    ),
                    parameters,
                )
                await database.execute(
                    text(
                        "UPDATE career.execution_attempts SET status=:status, "
                        "outcome=:outcome, finished_at=CASE WHEN :status='cancelled' "
                        "THEN clock_timestamp() ELSE finished_at END, "
                        "updated_at=clock_timestamp() WHERE task_id=:task AND user_id=:user"
                    ),
                    parameters,
                )
                result = await self._read(database, actor, task_id)
                assert result is not None
                return result
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Read execution storage is unavailable") from None

    async def reconcile_released(
        self, actor: ActorContext, task_id: UUID, *, allow_absent: bool = False
    ) -> ReadExecution:
        try:
            async with self.engine.begin() as database:
                execution = await self._read(database, actor, task_id, lock=True)
                if execution is None or not isinstance(execution.target, BossReadTarget):
                    raise ExecutionConflict("BOSS read execution is unavailable")
                if execution.task.status in {"failed", "cancelled"}:
                    return execution
                stopping = (
                    execution.task.status == "waiting"
                    and execution.attempt.status == "waiting"
                    and execution.attempt.outcome == "read_stop_requested"
                )
                if not stopping and (
                    execution.task.status != "unknown" or execution.attempt.status != "unknown"
                ):
                    raise ExecutionConflict("Read execution does not require reconciliation")
                released = await database.scalar(
                    text(
                        "SELECT true FROM browser.sessions s "
                        "LEFT JOIN browser.steel_operations o ON o.session_id=s.session_id "
                        "WHERE s.session_id=:session AND s.user_id=:user AND s.task_id=:task "
                        "AND s.authorization_id=:authorization AND s.revoked=true "
                        "AND s.lease_id IS NULL AND (o.state='released' OR o.session_id IS NULL) "
                        "FOR UPDATE OF s"
                    ),
                    {
                        "session": execution.attempt.browser_session_id,
                        "user": actor.user_id,
                        "task": task_id,
                        "authorization": execution.authorization.id,
                    },
                )
                if not released and allow_absent:
                    registered = await database.scalar(
                        text("SELECT true FROM browser.sessions WHERE session_id=:session"),
                        {"session": execution.attempt.browser_session_id},
                    )
                    released = not registered
                if not released:
                    raise ExecutionConflict("Browser release is not confirmed")
                parameters = {
                    "task": task_id,
                    "user": actor.user_id,
                    "status": "cancelled" if stopping else "failed",
                    "outcome": "cancelled_after_stop" if stopping else "read_failed",
                }
                await database.execute(
                    text(
                        "UPDATE career.execution_authorizations SET status='revoked', "
                        "revoked_at=clock_timestamp() WHERE task_id=:task AND user_id=:user"
                    ),
                    parameters,
                )
                await database.execute(
                    text(
                        "UPDATE career.execution_attempts SET status=:status, "
                        "outcome=:outcome, finished_at=COALESCE(finished_at,clock_timestamp()), "
                        "updated_at=clock_timestamp() "
                        "WHERE task_id=:task AND user_id=:user"
                    ),
                    parameters,
                )
                await database.execute(
                    text(
                        "UPDATE career.execution_tasks SET status=:status, "
                        "updated_at=clock_timestamp() WHERE id=:task AND user_id=:user"
                    ),
                    parameters,
                )
                result = await self._read(database, actor, task_id)
                assert result is not None
                return result
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Read reconciliation storage is unavailable") from None

    async def reserve_browser(
        self, actor: ActorContext, task_id: UUID, session_id: UUID
    ) -> BrowserControlContext:
        try:
            async with self.engine.begin() as database:
                execution = await self._read(database, actor, task_id, lock=True)
                if execution is None or not isinstance(execution.target, BossReadTarget):
                    raise ExecutionConflict("BOSS read execution is unavailable")
                now = cast(datetime, await database.scalar(text("SELECT clock_timestamp()")))
                if (
                    execution.task.status != "accepted"
                    or execution.attempt.status != "accepted"
                    or execution.authorization.status != "active"
                    or execution.authorization.expires_at <= now
                ):
                    raise ExecutionConflict("BOSS read execution cannot start")
                await self._validate_target(database, actor, execution.target)
                await database.execute(
                    text(
                        "UPDATE career.execution_attempts SET browser_session_id=:session, "
                        "status='running', started_at=clock_timestamp(), "
                        "updated_at=clock_timestamp() WHERE id=:attempt AND user_id=:user"
                    ),
                    {"session": session_id, "attempt": execution.attempt.id, "user": actor.user_id},
                )
                await database.execute(
                    text(
                        "UPDATE career.execution_tasks SET status='running', "
                        "updated_at=clock_timestamp() WHERE id=:task AND user_id=:user"
                    ),
                    {"task": task_id, "user": actor.user_id},
                )
                return BrowserControlContext(
                    user_id=actor.user_id,
                    session_id=session_id,
                    task_id=task_id,
                    authorization_id=execution.authorization.id,
                    authorization_expires_at=execution.authorization.expires_at,
                    attempt_id=execution.attempt.id,
                    request_id=execution.attempt.request_id,
                    owner_id="boss-read",
                    conversation_id=execution.target.conversation_id,
                )
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Read execution storage is unavailable") from None

    async def finish_browser(
        self,
        actor: ActorContext,
        task_id: UUID,
        *,
        outcome: str,
        observation: BossPageObservation | None = None,
    ) -> ReadExecution:
        if outcome not in {"read_completed", "read_failed", "read_unknown"}:
            raise ExecutionConflict("Unsupported read execution outcome")
        status = {
            "read_completed": "completed",
            "read_failed": "failed",
            "read_unknown": "unknown",
        }[outcome]
        try:
            async with self.engine.begin() as database:
                execution = await self._read(database, actor, task_id, lock=True)
                if execution is None:
                    raise ExecutionConflict("Read execution is unavailable")
                if execution.task.status in {"completed", "failed", "timed_out", "cancelled"}:
                    return execution
                if (
                    execution.task.status == "waiting"
                    and execution.attempt.outcome == "read_stop_requested"
                ):
                    return execution
                if execution.task.status != "running" or execution.attempt.status != "running":
                    raise ExecutionConflict("Read execution is not running")
                if observation is not None:
                    payload = json.dumps(asdict(observation), ensure_ascii=False)
                    if len(payload.encode()) > 512 * 1024:
                        raise ExecutionConflict("Read result exceeds its storage limit")
                    await database.execute(
                        text(
                            "INSERT INTO career.execution_read_results (task_id, user_id, page) "
                            "VALUES (:task, :user, CAST(:page AS jsonb))"
                        ),
                        {"task": task_id, "user": actor.user_id, "page": payload},
                    )
                await database.execute(
                    text(
                        "UPDATE career.execution_authorizations SET status='revoked', "
                        "revoked_at=COALESCE(revoked_at,clock_timestamp()) "
                        "WHERE task_id=:task AND user_id=:user"
                    ),
                    {"task": task_id, "user": actor.user_id},
                )
                await database.execute(
                    text(
                        "UPDATE career.execution_attempts SET status=:status, outcome=:outcome, "
                        "finished_at=clock_timestamp(), updated_at=clock_timestamp() "
                        "WHERE id=:attempt AND user_id=:user"
                    ),
                    {
                        "status": status,
                        "outcome": outcome,
                        "attempt": execution.attempt.id,
                        "user": actor.user_id,
                    },
                )
                await database.execute(
                    text(
                        "UPDATE career.execution_tasks SET status=:status, "
                        "updated_at=clock_timestamp() WHERE id=:task AND user_id=:user"
                    ),
                    {"status": status, "task": task_id, "user": actor.user_id},
                )
                result = await self._read(database, actor, task_id)
                assert result is not None
                return result
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Read execution storage is unavailable") from None

    async def read_latest_boss(
        self, actor: ActorContext, connection_id: UUID
    ) -> ReadExecution | None:
        try:
            async with self.engine.connect() as database:
                task_id = await database.scalar(
                    text(
                        "SELECT t.id FROM career.execution_tasks t "
                        "JOIN career.execution_resources r ON r.task_id=t.id "
                        "AND r.user_id=t.user_id "
                        "WHERE t.user_id=:user AND t.kind='boss_read' "
                        "AND r.kind='boss_connection' AND r.connection_id=:connection "
                        "ORDER BY CASE WHEN t.status IN ('accepted','running','waiting','unknown') "
                        "THEN 0 ELSE 1 END, t.created_at DESC, t.id DESC LIMIT 1"
                    ),
                    {"user": actor.user_id, "connection": connection_id},
                )
                return await self._read(database, actor, task_id) if task_id is not None else None
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Read execution storage is unavailable") from None

    async def read_page_result(self, actor: ActorContext, task_id: UUID) -> ReadPageResult | None:
        try:
            async with self.engine.connect() as database:
                row = (
                    (
                        await database.execute(
                            text(
                                "SELECT observed_at, page FROM career.execution_read_results "
                                "WHERE task_id=:task AND user_id=:user"
                            ),
                            {"task": task_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return None
                page = TypeAdapter(BossPageObservation).validate_json(json.dumps(row["page"]))
                return ReadPageResult(row["observed_at"], page)
        except (DBAPIError, PoolTimeoutError, ValidationError):
            raise ExecutionUnavailable("Read result storage is unavailable") from None
