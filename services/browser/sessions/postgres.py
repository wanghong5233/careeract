import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from services.browser.sessions.authentication import BrowserCommand, CommandRejected
from services.browser.sessions.lease import LeaseConflict, LeaseNotFound, SessionLease


class PostgresLeaseStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def register(
        self, session_id: UUID, user_id: str, task_id: UUID, authorization_id: UUID
    ) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO browser.sessions (session_id, user_id, task_id, authorization_id) "
                    "VALUES (:session, :user, :task, :authorization)"
                ),
                {
                    "session": session_id,
                    "user": user_id,
                    "task": task_id,
                    "authorization": authorization_id,
                },
            )

    async def execute(self, command: BrowserCommand) -> SessionLease:
        if command.action not in ("acquire", "renew", "stop", "check"):
            raise CommandRejected("Not a lease command")
        async with self.engine.begin() as connection:
            row = await self._lock(connection, command.session_id)
            now = cast(datetime, await connection.scalar(text("SELECT clock_timestamp()")))
            if (
                row["revoked"]
                or row["user_id"] != command.sub
                or row["task_id"] != command.task_id
                or row["authorization_id"] != command.authorization_id
                or not command.is_current(now.timestamp())
            ):
                raise CommandRejected("Browser command is no longer authorized")
            if command.action != "check":
                consumed = await connection.scalar(
                    text(
                        "INSERT INTO browser.commands (command_id, session_id, request_id, action) "
                        "VALUES (:command, :session, :request, :action) "
                        "ON CONFLICT (command_id) DO NOTHING RETURNING command_id"
                    ),
                    {
                        "command": command.jti,
                        "session": command.session_id,
                        "request": command.request_id,
                        "action": command.action,
                    },
                )
                if consumed is None:
                    raise CommandRejected("Browser command was already consumed")
            lease_id = row["lease_id"]
            expires_at = min(now + timedelta(seconds=30), datetime.fromtimestamp(command.exp, UTC))
            if command.action == "acquire":
                if lease_id is not None or command.lease_id is not None:
                    raise LeaseConflict("Previous writer must be stopped before acquisition")
                lease_id = uuid4()
                await connection.execute(
                    text(
                        "UPDATE browser.sessions SET lease_id=:lease, owner_id=:owner, "
                        "attempt_id=:attempt, expires_at=:expires WHERE session_id=:session"
                    ),
                    {
                        "lease": lease_id,
                        "owner": command.owner_id,
                        "attempt": command.attempt_id,
                        "expires": expires_at,
                        "session": command.session_id,
                    },
                )
                return SessionLease(command.session_id, lease_id, command.owner_id, expires_at)
            if lease_id is None:
                raise LeaseNotFound("Session lease not found")
            if (
                lease_id != command.lease_id
                or row["owner_id"] != command.owner_id
                or row["attempt_id"] != command.attempt_id
            ):
                raise LeaseConflict("Lease does not belong to this executor attempt")
            current = SessionLease(
                command.session_id, lease_id, row["owner_id"], row["expires_at"], row["draining"]
            )
            if command.action == "stop":
                await connection.execute(
                    text("UPDATE browser.sessions SET draining=true WHERE session_id=:session"),
                    {"session": command.session_id},
                )
                return SessionLease(
                    current.session_id, current.lease_id, current.owner_id, current.expires_at, True
                )
            if not current.is_active(now):
                raise LeaseConflict("Expired or draining lease cannot write or renew")
            if command.action == "renew":
                await connection.execute(
                    text(
                        "UPDATE browser.sessions SET expires_at=:expires WHERE session_id=:session"
                    ),
                    {"expires": expires_at, "session": command.session_id},
                )
                return SessionLease(
                    current.session_id, current.lease_id, current.owner_id, expires_at
                )
            return current

    async def authorize_viewer(self, command: BrowserCommand) -> None:
        if command.action != "viewer" or command.lease_id is not None:
            raise CommandRejected("Not a viewer command")
        async with self.engine.begin() as connection:
            row = await self._lock(connection, command.session_id)
            now = cast(datetime, await connection.scalar(text("SELECT clock_timestamp()")))
            if (
                row["revoked"]
                or row["user_id"] != command.sub
                or row["task_id"] != command.task_id
                or row["authorization_id"] != command.authorization_id
                or not command.is_current(now.timestamp())
            ):
                raise CommandRejected("Browser command is no longer authorized")
            if row["lease_id"] is not None:
                raise LeaseConflict("Previous writer must be stopped before viewing")

    async def acquire_viewer(self, command: BrowserCommand) -> SessionLease:
        if command.action != "viewer" or command.lease_id is not None:
            raise CommandRejected("Not a viewer command")
        return await self.execute(command.model_copy(update={"action": "acquire"}))

    async def renew_viewer(self, command: BrowserCommand, lease_id: UUID) -> None:
        if command.action != "viewer" or command.lease_id is not None:
            raise CommandRejected("Not a viewer command")
        await self.execute(
            command.model_copy(update={"action": "renew", "lease_id": lease_id, "jti": uuid4()})
        )

    async def check_viewer(self, command: BrowserCommand, lease_id: UUID) -> None:
        if command.action != "viewer" or command.lease_id is not None:
            raise CommandRejected("Not a viewer command")
        await self.execute(command.model_copy(update={"action": "check", "lease_id": lease_id}))

    async def refresh_viewer(self, command: BrowserCommand, lease_id: UUID) -> None:
        if command.action != "viewer" or command.lease_id is not None:
            raise CommandRejected("Not a viewer command")
        await self.execute(command.model_copy(update={"action": "renew", "lease_id": lease_id}))

    async def drain_viewer(self, command: BrowserCommand, lease_id: UUID) -> None:
        if command.action != "viewer" or command.lease_id is not None:
            raise CommandRejected("Not a viewer command")
        async with self.engine.begin() as connection:
            row = await self._lock(connection, command.session_id)
            if (
                row["lease_id"] != lease_id
                or row["owner_id"] != command.owner_id
                or row["attempt_id"] != command.attempt_id
                or row["user_id"] != command.sub
                or row["task_id"] != command.task_id
                or row["authorization_id"] != command.authorization_id
            ):
                raise LeaseConflict("Viewer lease does not belong to this connection")
            await connection.execute(
                text("UPDATE browser.sessions SET draining=true WHERE session_id=:session"),
                {"session": command.session_id},
            )

    async def manage(self, command: BrowserCommand) -> None:
        if command.action not in ("register", "revoke") or command.lease_id is not None:
            raise CommandRejected("Not a session command")
        async with self.engine.begin() as connection:
            created = await connection.scalar(
                text(
                    "INSERT INTO browser.sessions "
                    "(session_id, user_id, task_id, authorization_id, revoked) "
                    "VALUES (:session, :user, :task, :authorization, :revoked) "
                    "ON CONFLICT (session_id) DO NOTHING RETURNING session_id"
                ),
                {
                    "session": command.session_id,
                    "user": command.sub,
                    "task": command.task_id,
                    "authorization": command.authorization_id,
                    "revoked": command.action == "revoke",
                },
            )
            row = await self._lock(connection, command.session_id)
            now = cast(datetime, await connection.scalar(text("SELECT clock_timestamp()")))
            if (
                row["user_id"] != command.sub
                or row["task_id"] != command.task_id
                or row["authorization_id"] != command.authorization_id
                or not command.is_current(now.timestamp())
            ):
                raise CommandRejected("Browser command is no longer authorized")
            consumed = await connection.scalar(
                text(
                    "INSERT INTO browser.commands (command_id, session_id, request_id, action) "
                    "VALUES (:command, :session, :request, :action) "
                    "ON CONFLICT (command_id) DO NOTHING RETURNING command_id"
                ),
                {
                    "command": command.jti,
                    "session": command.session_id,
                    "request": command.request_id,
                    "action": command.action,
                },
            )
            if consumed is None:
                raise CommandRejected("Browser command was already consumed")
            if command.action == "register":
                if created is None:
                    raise LeaseConflict("Session already exists and cannot be rebound")
            else:
                await connection.execute(
                    text(
                        "UPDATE browser.sessions SET revoked=true, draining=(lease_id IS NOT NULL) "
                        "WHERE session_id=:session"
                    ),
                    {"session": command.session_id},
                )

    async def authorize_lifecycle(self, command: BrowserCommand) -> None:
        if command.action not in ("create", "release", "finish") or command.lease_id is not None:
            raise CommandRejected("Not a lifecycle command")
        async with self.engine.begin() as connection:
            row = await self._lock(connection, command.session_id)
            now = cast(datetime, await connection.scalar(text("SELECT clock_timestamp()")))
            if (
                row["user_id"] != command.sub
                or row["task_id"] != command.task_id
                or row["authorization_id"] != command.authorization_id
                or not command.is_current(now.timestamp())
                or (command.action == "create" and row["revoked"])
                or (command.action in ("release", "finish") and not row["revoked"])
            ):
                raise CommandRejected("Browser lifecycle is no longer authorized")
            if row["lease_id"] is not None:
                raise LeaseConflict("Previous writer must disconnect before lifecycle changes")
            consumed = await connection.scalar(
                text(
                    "INSERT INTO browser.commands (command_id, session_id, request_id, action) "
                    "VALUES (:command, :session, :request, :action) "
                    "ON CONFLICT (command_id) DO NOTHING RETURNING command_id"
                ),
                {
                    "command": command.jti,
                    "session": command.session_id,
                    "request": command.request_id,
                    "action": command.action,
                },
            )
            if consumed is None:
                raise CommandRejected("Browser command was already consumed")

    async def wait_for_viewer_stop(self, command: BrowserCommand) -> None:
        if command.action not in ("release", "finish"):
            raise CommandRejected("Only release can wait for disconnection")
        try:
            async with asyncio.timeout(7):
                while True:
                    async with self.engine.begin() as connection:
                        row = await self._lock(connection, command.session_id)
                        now = cast(
                            datetime, await connection.scalar(text("SELECT clock_timestamp()"))
                        )
                        if (
                            not row["revoked"]
                            or row["user_id"] != command.sub
                            or row["task_id"] != command.task_id
                            or row["authorization_id"] != command.authorization_id
                            or not command.is_current(now.timestamp())
                        ):
                            raise CommandRejected("Release is no longer authorized")
                        if row["lease_id"] is None:
                            return
                        if row["owner_id"] != "viewer":
                            raise LeaseConflict("Automatic executor requires reconciliation")
                    await asyncio.sleep(0.1)
        except TimeoutError:
            raise LeaseConflict("Viewer disconnection requires reconciliation") from None

    @asynccontextmanager
    async def lifecycle_guard(self, command: BrowserCommand) -> AsyncIterator[None]:
        async with self.engine.begin() as connection:
            row = await self._lock(connection, command.session_id)
            now = cast(datetime, await connection.scalar(text("SELECT clock_timestamp()")))
            if (
                command.action not in ("create", "release", "finish")
                or command.lease_id is not None
                or row["user_id"] != command.sub
                or row["task_id"] != command.task_id
                or row["authorization_id"] != command.authorization_id
                or not command.is_current(now.timestamp())
                or row["revoked"] != (command.action in ("release", "finish"))
            ):
                raise CommandRejected("Browser lifecycle is no longer authorized")
            if row["lease_id"] is not None:
                raise LeaseConflict("Previous writer must disconnect before lifecycle changes")
            yield

    async def revoke(self, session_id: UUID) -> None:
        async with self.engine.begin() as connection:
            await self._lock(connection, session_id)
            await connection.execute(
                text(
                    "UPDATE browser.sessions SET revoked=true, draining=(lease_id IS NOT NULL) "
                    "WHERE session_id=:session"
                ),
                {"session": session_id},
            )

    async def confirm_stopped(self, session_id: UUID, lease_id: UUID) -> None:
        async with self.engine.begin() as connection:
            row = await self._lock(connection, session_id)
            if row["lease_id"] != lease_id or not row["draining"]:
                raise LeaseConflict("Only the draining executor can be released")
            await connection.execute(
                text(
                    "UPDATE browser.sessions SET lease_id=NULL, owner_id=NULL, attempt_id=NULL, "
                    "expires_at=NULL, draining=false WHERE session_id=:session"
                ),
                {"session": session_id},
            )

    @staticmethod
    async def _lock(connection: AsyncConnection, session_id: UUID) -> RowMapping:
        row = (
            (
                await connection.execute(
                    text("SELECT * FROM browser.sessions WHERE session_id=:session FOR UPDATE"),
                    {"session": session_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise LeaseNotFound("Session not found")
        return row
