from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from services.api.application.context import ActorContext
from services.api.application.ports.browser_control import BrowserControlContext
from services.api.domain.boss_connection import BossConnectionNotFound
from services.api.domain.execution import (
    ExecutionAttempt,
    ExecutionAuthorization,
    ExecutionConflict,
    ExecutionTask,
    ExecutionUnavailable,
    LoginExecution,
)


def task_from_row(row: RowMapping) -> ExecutionTask:
    return ExecutionTask(
        id=row["id"],
        user_id=row["user_id"],
        kind=row["kind"],
        request_key=row["request_key"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        connection_id=row["connection_id"],
    )


def authorization_from_row(row: RowMapping) -> ExecutionAuthorization:
    return ExecutionAuthorization(
        id=row["id"],
        task_id=row["task_id"],
        user_id=row["user_id"],
        scope=row["scope"],
        status=row["status"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
    )


def attempt_from_row(row: RowMapping) -> ExecutionAttempt:
    return ExecutionAttempt(
        id=row["id"],
        task_id=row["task_id"],
        authorization_id=row["authorization_id"],
        user_id=row["user_id"],
        request_id=row["request_id"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        browser_session_id=row["browser_session_id"],
        outcome=row["outcome"],
    )


class PostgresExecutionRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def accept(
        self,
        actor: ActorContext,
        *,
        connection_id: UUID,
        kind: str,
        request_key: UUID,
        scope: str,
        authorization_expires_at: datetime,
        request_id: UUID,
        expected_version: UUID | None = None,
    ) -> tuple[ExecutionTask, ExecutionAuthorization, ExecutionAttempt]:
        if kind != "boss_login" or scope != "boss.login":
            raise ExecutionConflict("Unsupported execution scope")
        if authorization_expires_at.utcoffset() is None:
            raise ExecutionConflict("Execution authorization requires a timezone")
        try:
            async with self.engine.begin() as database:
                await database.execute(
                    text('SELECT id FROM auth."user" WHERE id=:user_id FOR UPDATE'),
                    {"user_id": actor.user_id},
                )
                existing = (
                    (
                        await database.execute(
                            text(
                                "SELECT * FROM career.execution_tasks "
                                "WHERE user_id=:user_id AND request_key=:key FOR UPDATE"
                            ),
                            {"user_id": actor.user_id, "key": request_key},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing is not None:
                    if existing["connection_id"] != connection_id or existing["kind"] != kind:
                        raise ExecutionConflict("Execution request key has different content")
                    authorization = (
                        (
                            await database.execute(
                                text(
                                    "SELECT * FROM career.execution_authorizations "
                                    "WHERE task_id=:task"
                                ),
                                {"task": existing["id"]},
                            )
                        )
                        .mappings()
                        .one()
                    )
                    attempt = (
                        (
                            await database.execute(
                                text("SELECT * FROM career.execution_attempts WHERE task_id=:task"),
                                {"task": existing["id"]},
                            )
                        )
                        .mappings()
                        .one()
                    )
                    if authorization["scope"] != scope:
                        raise ExecutionConflict("Execution request key has different scope")
                    return (
                        task_from_row(existing),
                        authorization_from_row(authorization),
                        attempt_from_row(attempt),
                    )
                connection = (
                    (
                        await database.execute(
                            text(
                                "SELECT * FROM career.boss_connections "
                                "WHERE id=:id AND user_id=:user_id FOR UPDATE"
                            ),
                            {"id": connection_id, "user_id": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if connection is None:
                    raise BossConnectionNotFound("BOSS connection does not exist")
                if (
                    connection["status"] != "pending"
                    or connection["browser_session_id"] is not None
                    or (expected_version is not None and connection["version"] != expected_version)
                ):
                    raise ExecutionConflict("BOSS connection is unavailable for login")
                now = await database.scalar(text("SELECT clock_timestamp()"))
                duration = (authorization_expires_at - now).total_seconds()
                if not 0 < duration <= 15 * 60:
                    raise ExecutionConflict("Login authorization must expire within 15 minutes")
                task = (
                    (
                        await database.execute(
                            text(
                                "INSERT INTO career.execution_tasks "
                                "(id,user_id,connection_id,kind,request_key) "
                                "VALUES (:id,:user_id,:connection,:kind,:key) RETURNING *"
                            ),
                            {
                                "id": uuid4(),
                                "user_id": actor.user_id,
                                "connection": connection_id,
                                "kind": kind,
                                "key": request_key,
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                authorization = (
                    (
                        await database.execute(
                            text(
                                "INSERT INTO career.execution_authorizations "
                                "(id,task_id,user_id,scope,expires_at) "
                                "VALUES (:id,:task,:user_id,:scope,:expires) RETURNING *"
                            ),
                            {
                                "id": uuid4(),
                                "task": task["id"],
                                "user_id": actor.user_id,
                                "scope": scope,
                                "expires": authorization_expires_at,
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                attempt = (
                    (
                        await database.execute(
                            text(
                                "INSERT INTO career.execution_attempts "
                                "(id,task_id,authorization_id,user_id,request_id) "
                                "VALUES (:id,:task,:authorization,:user_id,:request) RETURNING *"
                            ),
                            {
                                "id": uuid4(),
                                "task": task["id"],
                                "authorization": authorization["id"],
                                "user_id": actor.user_id,
                                "request": request_id,
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                return (
                    task_from_row(task),
                    authorization_from_row(authorization),
                    attempt_from_row(attempt),
                )
        except IntegrityError:
            raise ExecutionConflict(
                "Execution request conflicts with an existing attempt"
            ) from None
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Execution state is unavailable") from None

    async def read_attempt(self, actor: ActorContext, attempt_id: UUID) -> ExecutionAttempt | None:
        try:
            async with self.engine.connect() as database:
                row = (
                    (
                        await database.execute(
                            text(
                                "SELECT * FROM career.execution_attempts "
                                "WHERE id=:id AND user_id=:user_id"
                            ),
                            {"id": attempt_id, "user_id": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return attempt_from_row(row) if row is not None else None
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Execution state is unavailable") from None

    @staticmethod
    async def _lock(database: AsyncConnection, actor: ActorContext, attempt_id: UUID) -> RowMapping:
        await database.execute(
            text(
                "SELECT c.id FROM career.boss_connections c "
                "JOIN career.execution_tasks t ON t.connection_id=c.id AND t.user_id=c.user_id "
                "JOIN career.execution_attempts a ON a.task_id=t.id AND a.user_id=t.user_id "
                "WHERE a.id=:id AND a.user_id=:user_id FOR UPDATE OF c"
            ),
            {"id": attempt_id, "user_id": actor.user_id},
        )
        row = (
            (
                await database.execute(
                    text(
                        "SELECT a.*, t.status AS task_status, t.connection_id, "
                        "c.status AS connection_status, "
                        "c.version AS connection_version, "
                        "z.status AS authorization_status, "
                        "z.expires_at AS authorization_expires_at "
                        "FROM career.execution_tasks t "
                        "JOIN career.boss_connections c "
                        "ON c.id=t.connection_id AND c.user_id=t.user_id "
                        "JOIN career.execution_authorizations z "
                        "ON z.task_id=t.id AND z.user_id=t.user_id "
                        "JOIN career.execution_attempts a ON a.authorization_id=z.id "
                        "AND a.task_id=t.id AND a.user_id=t.user_id "
                        "WHERE a.id=:id AND a.user_id=:user_id FOR UPDATE OF t,z,a"
                    ),
                    {"id": attempt_id, "user_id": actor.user_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ExecutionConflict("Execution attempt is unavailable")
        return row

    async def bind_browser_session(
        self, actor: ActorContext, attempt_id: UUID, session_id: UUID
    ) -> BrowserControlContext:
        try:
            async with self.engine.begin() as database:
                row = await self._lock(database, actor, attempt_id)
                now = await database.scalar(text("SELECT clock_timestamp()"))
                if (
                    row["browser_session_id"] is not None
                    or row["status"] != "accepted"
                    or row["task_status"] != "accepted"
                    or row["connection_status"] != "pending"
                    or row["authorization_status"] != "active"
                    or row["authorization_expires_at"] <= now
                ):
                    raise ExecutionConflict("Execution attempt cannot start or be retried")
                await database.execute(
                    text(
                        "UPDATE career.execution_attempts SET browser_session_id=:session, "
                        "status='running', started_at=clock_timestamp(), "
                        "updated_at=clock_timestamp() WHERE id=:id"
                    ),
                    {"id": attempt_id, "session": session_id},
                )
                await database.execute(
                    text(
                        "UPDATE career.execution_tasks SET status='running', "
                        "updated_at=clock_timestamp() WHERE id=:id"
                    ),
                    {"id": row["task_id"]},
                )
                return BrowserControlContext(
                    user_id=actor.user_id,
                    session_id=session_id,
                    task_id=row["task_id"],
                    authorization_id=row["authorization_id"],
                    authorization_expires_at=row["authorization_expires_at"],
                    attempt_id=attempt_id,
                    request_id=row["request_id"],
                    owner_id="boss-login",
                )
        except IntegrityError:
            raise ExecutionConflict("Browser session is already bound") from None
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Execution state is unavailable") from None

    async def record_registration(
        self,
        actor: ActorContext,
        attempt_id: UUID,
        outcome: Literal["browser_registered", "registration_unconfirmed", "registration_rejected"],
    ) -> ExecutionAttempt:
        if outcome not in (
            "browser_registered",
            "registration_unconfirmed",
            "registration_rejected",
        ):
            raise ExecutionConflict("Unsupported registration evidence")
        try:
            async with self.engine.begin() as database:
                row = await self._lock(database, actor, attempt_id)
                if row["status"] != "running" or row["browser_session_id"] is None:
                    raise ExecutionConflict("Registration result cannot replace existing evidence")
                now = await database.scalar(text("SELECT clock_timestamp()"))
                status = {
                    "browser_registered": "waiting",
                    "registration_unconfirmed": "unknown",
                    "registration_rejected": "failed",
                }[outcome]
                evidence: str = outcome
                if (
                    row["task_status"] == "cancelled"
                    or row["connection_status"] in ("revoked", "failed")
                    or row["authorization_status"] != "active"
                    or row["authorization_expires_at"] <= now
                ):
                    status, evidence = "unknown", "cleanup_required"
                updated = (
                    (
                        await database.execute(
                            text(
                                "UPDATE career.execution_attempts "
                                "SET status=:status, outcome=:outcome, "
                                "finished_at=CASE WHEN :status='waiting' THEN NULL "
                                "ELSE clock_timestamp() END, "
                                "updated_at=clock_timestamp() WHERE id=:id RETURNING *"
                            ),
                            {"id": attempt_id, "status": status, "outcome": evidence},
                        )
                    )
                    .mappings()
                    .one()
                )
                if row["task_status"] != "cancelled":
                    await database.execute(
                        text(
                            "UPDATE career.execution_tasks SET status=:status, "
                            "updated_at=clock_timestamp() WHERE id=:id"
                        ),
                        {
                            "id": row["task_id"],
                            "status": "failed" if status == "failed" else "waiting",
                        },
                    )
                return attempt_from_row(updated)
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Execution state is unavailable") from None

    async def revoke(
        self, actor: ActorContext, attempt_id: UUID, *, expected_version: UUID | None = None
    ) -> ExecutionAttempt:
        try:
            async with self.engine.begin() as database:
                row = await self._lock(database, actor, attempt_id)
                if row["authorization_status"] == "revoked":
                    return attempt_from_row(row)
                if expected_version is not None and row["connection_version"] != expected_version:
                    raise ExecutionConflict("BOSS connection has changed")
                await database.execute(
                    text(
                        "UPDATE career.execution_authorizations SET status='revoked', "
                        "revoked_at=clock_timestamp() WHERE id=:id"
                    ),
                    {"id": row["authorization_id"]},
                )
                await database.execute(
                    text(
                        "UPDATE career.execution_tasks SET status='cancelled', "
                        "updated_at=clock_timestamp() WHERE id=:id"
                    ),
                    {"id": row["task_id"]},
                )
                updated = (
                    (
                        await database.execute(
                            text(
                                "UPDATE career.execution_attempts "
                                "SET status=:status, outcome=:outcome, "
                                "finished_at=clock_timestamp(), updated_at=clock_timestamp() "
                                "WHERE id=:id RETURNING *"
                            ),
                            {
                                "id": attempt_id,
                                "status": "cancelled" if row["started_at"] is None else "unknown",
                                "outcome": "cancelled_before_start"
                                if row["started_at"] is None
                                else "cleanup_required",
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                await database.execute(
                    text(
                        "UPDATE career.boss_connections SET status=:status, "
                        "last_observed_state=:outcome, version=:version, "
                        "updated_at=clock_timestamp() WHERE id=:id"
                    ),
                    {
                        "id": row["connection_id"],
                        "status": "revoked" if row["started_at"] is None else "blocked",
                        "outcome": "cancelled_before_start"
                        if row["started_at"] is None
                        else "cleanup_required",
                        "version": uuid4(),
                    },
                )
                return attempt_from_row(updated)
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Execution state is unavailable") from None

    async def read_login(self, actor: ActorContext, connection_id: UUID) -> LoginExecution | None:
        try:
            async with self.engine.begin() as database:
                await database.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                owned = await database.scalar(
                    text("SELECT id FROM career.boss_connections WHERE id=:id AND user_id=:user"),
                    {"id": connection_id, "user": actor.user_id},
                )
                if owned is None:
                    raise BossConnectionNotFound("BOSS connection does not exist")
                task = (
                    (
                        await database.execute(
                            text(
                                "SELECT * FROM career.execution_tasks t "
                                "WHERE t.connection_id=:id AND t.user_id=:user"
                            ),
                            {"id": connection_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if task is None:
                    return None
                parameters = {"task": task["id"], "user": actor.user_id}
                authorization = (
                    (
                        await database.execute(
                            text(
                                "SELECT * FROM career.execution_authorizations "
                                "WHERE task_id=:task AND user_id=:user"
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
                                "WHERE task_id=:task AND user_id=:user"
                            ),
                            parameters,
                        )
                    )
                    .mappings()
                    .one()
                )
                return LoginExecution(
                    task_from_row(task),
                    authorization_from_row(authorization),
                    attempt_from_row(attempt),
                )
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Execution state is unavailable") from None

    async def reserve_creation(
        self, actor: ActorContext, attempt_id: UUID
    ) -> BrowserControlContext:
        try:
            async with self.engine.begin() as database:
                row = await self._lock(database, actor, attempt_id)
                now = await database.scalar(text("SELECT clock_timestamp()"))
                if (
                    row["browser_session_id"] is None
                    or row["status"] != "waiting"
                    or row["task_status"] != "waiting"
                    or row["outcome"] != "browser_registered"
                    or row["connection_status"] != "pending"
                    or row["authorization_status"] != "active"
                    or row["authorization_expires_at"] <= now
                ):
                    raise ExecutionConflict("Browser creation cannot start or be retried")
                await database.execute(
                    text(
                        "UPDATE career.execution_attempts SET status='running', "
                        "outcome='browser_creating', updated_at=clock_timestamp() WHERE id=:id"
                    ),
                    {"id": attempt_id},
                )
                await database.execute(
                    text(
                        "UPDATE career.execution_tasks SET status='running', "
                        "updated_at=clock_timestamp() WHERE id=:id"
                    ),
                    {"id": row["task_id"]},
                )
                await database.execute(
                    text(
                        "UPDATE career.boss_connections SET browser_session_id=:session, "
                        "version=:version, last_observed_state='browser_creating', "
                        "updated_at=clock_timestamp() WHERE id=:id"
                    ),
                    {
                        "id": row["connection_id"],
                        "session": row["browser_session_id"],
                        "version": uuid4(),
                    },
                )
                return BrowserControlContext(
                    user_id=actor.user_id,
                    session_id=row["browser_session_id"],
                    task_id=row["task_id"],
                    authorization_id=row["authorization_id"],
                    authorization_expires_at=row["authorization_expires_at"],
                    attempt_id=attempt_id,
                    request_id=row["request_id"],
                    owner_id="boss-login",
                )
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Execution state is unavailable") from None

    async def record_creation(
        self,
        actor: ActorContext,
        attempt_id: UUID,
        outcome: Literal["browser_created", "creation_unconfirmed", "creation_rejected"],
    ) -> ExecutionAttempt:
        if outcome not in ("browser_created", "creation_unconfirmed", "creation_rejected"):
            raise ExecutionConflict("Unsupported browser creation evidence")
        try:
            async with self.engine.begin() as database:
                row = await self._lock(database, actor, attempt_id)
                if row["outcome"] not in ("browser_creating", "cleanup_required"):
                    raise ExecutionConflict("Creation result cannot replace existing evidence")
                now = await database.scalar(text("SELECT clock_timestamp()"))
                evidence: str = outcome
                status = "waiting" if outcome == "browser_created" else "unknown"
                if (
                    row["task_status"] == "cancelled"
                    or row["connection_status"] in ("revoked", "failed")
                    or row["authorization_status"] != "active"
                    or row["authorization_expires_at"] <= now
                ):
                    status, evidence = "unknown", "cleanup_required"
                updated = (
                    (
                        await database.execute(
                            text(
                                "UPDATE career.execution_attempts SET status=:status, "
                                "outcome=:outcome, finished_at=CASE WHEN :status='waiting' "
                                "THEN NULL ELSE clock_timestamp() END, "
                                "updated_at=clock_timestamp() WHERE id=:id RETURNING *"
                            ),
                            {"id": attempt_id, "status": status, "outcome": evidence},
                        )
                    )
                    .mappings()
                    .one()
                )
                if row["task_status"] != "cancelled":
                    await database.execute(
                        text(
                            "UPDATE career.execution_tasks SET status='waiting', "
                            "updated_at=clock_timestamp() WHERE id=:id"
                        ),
                        {"id": row["task_id"]},
                    )
                if row["connection_status"] not in ("revoked", "failed"):
                    await database.execute(
                        text(
                            "UPDATE career.boss_connections SET status=:status, "
                            "last_observed_state=:outcome, version=:version, "
                            "updated_at=clock_timestamp() WHERE id=:id"
                        ),
                        {
                            "id": row["connection_id"],
                            "status": "waiting_for_login" if status == "waiting" else "blocked",
                            "outcome": evidence,
                            "version": uuid4(),
                        },
                    )
                return attempt_from_row(updated)
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Execution state is unavailable") from None

    async def forget_context(
        self, actor: ActorContext, attempt_id: UUID, *, expected_version: UUID
    ) -> BrowserControlContext | None:
        try:
            async with self.engine.begin() as database:
                row = await self._lock(database, actor, attempt_id)
                if row["connection_status"] == "revoked":
                    return None
                if (
                    row["connection_status"] != "connected"
                    or row["connection_version"] != expected_version
                    or row["authorization_status"] != "revoked"
                    or row["outcome"] != "browser_released"
                    or row["browser_session_id"] is None
                ):
                    raise ExecutionConflict("Saved login requires a released owned connection")
                return BrowserControlContext(
                    actor.user_id,
                    row["browser_session_id"],
                    row["task_id"],
                    row["authorization_id"],
                    row["authorization_expires_at"],
                    attempt_id,
                    UUID(actor.request_id),
                    "boss-login",
                )
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Saved login state is unavailable") from None

    async def record_forget(
        self, actor: ActorContext, attempt_id: UUID, *, expected_version: UUID
    ) -> None:
        try:
            async with self.engine.begin() as database:
                row = await self._lock(database, actor, attempt_id)
                if row["connection_status"] == "revoked":
                    return
                if (
                    row["connection_status"] != "connected"
                    or row["connection_version"] != expected_version
                ):
                    raise ExecutionConflict("Saved login connection changed")
                await database.execute(
                    text(
                        "UPDATE career.boss_connections SET status='revoked',"
                        "last_observed_state='saved_login_forgotten',version=:version,"
                        "updated_at=clock_timestamp() WHERE id=:id AND user_id=:user"
                    ),
                    {"id": row["connection_id"], "user": actor.user_id, "version": uuid4()},
                )
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Saved login result requires reconciliation") from None

    async def record_release(
        self, actor: ActorContext, attempt_id: UUID, *, login_verified: bool = False
    ) -> ExecutionAttempt:
        try:
            async with self.engine.begin() as database:
                row = await self._lock(database, actor, attempt_id)
                if row["outcome"] == "browser_released":
                    return attempt_from_row(row)
                if row["authorization_status"] != "revoked" or row["outcome"] != "cleanup_required":
                    raise ExecutionConflict("Browser release is not authorized")
                updated = (
                    (
                        await database.execute(
                            text(
                                "UPDATE career.execution_attempts SET status=:status, "
                                "outcome='browser_released', finished_at=clock_timestamp(), "
                                "updated_at=clock_timestamp() WHERE id=:id RETURNING *"
                            ),
                            {
                                "id": attempt_id,
                                "status": "completed" if login_verified else "cancelled",
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                await database.execute(
                    text(
                        "UPDATE career.boss_connections SET status=:status, "
                        "last_observed_state=:observed, version=:version, "
                        "updated_at=clock_timestamp() WHERE id=:id"
                    ),
                    {
                        "id": row["connection_id"],
                        "version": uuid4(),
                        "status": "connected" if login_verified else "revoked",
                        "observed": "login_verified_and_saved"
                        if login_verified
                        else "browser_released",
                    },
                )
                if login_verified:
                    await database.execute(
                        text(
                            "UPDATE career.execution_tasks SET status='completed', "
                            "updated_at=clock_timestamp() WHERE id=:id"
                        ),
                        {"id": row["task_id"]},
                    )
                return attempt_from_row(updated)
        except (DBAPIError, PoolTimeoutError):
            raise ExecutionUnavailable("Execution state is unavailable") from None
