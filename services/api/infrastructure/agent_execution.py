import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from services.api.application.context import ActorContext
from services.api.application.work_sessions import AgentWorkSessionService
from services.api.domain.work_session import (
    AgentWorkSession,
    WorkSessionConflict,
    WorkSessionNotFound,
    WorkSessionUnavailable,
)


async def lock_conversation(connection: AsyncConnection, session_id: str) -> None:
    locked = await connection.scalar(
        text(
            "SELECT pg_try_advisory_xact_lock("
            "hashtext('careeract_conversation'), hashtext(:session_id))"
        ),
        {"session_id": session_id},
    )
    if not locked:
        raise WorkSessionConflict("Conversation has an active request")


async def lock_runtime(connection: AsyncConnection, name: str, value: str) -> None:
    locked = await connection.scalar(
        text("SELECT pg_try_advisory_lock(hashtext(:name), hashtext(:value))"),
        {"name": name, "value": value},
    )
    if not locked:
        raise WorkSessionConflict("Conversation has an active request")


async def unlock_runtime(connection: AsyncConnection, name: str, value: str) -> None:
    await connection.scalar(
        text("SELECT pg_advisory_unlock(hashtext(:name), hashtext(:value))"),
        {"name": name, "value": value},
    )


class AgentExecution:
    def __init__(self, engine: AsyncEngine, sessions: AgentWorkSessionService, agent: Any) -> None:
        self.engine, self.sessions, self.agent = engine, sessions, agent

    async def cancel(self, actor: ActorContext, session_id: str, run_id: str) -> str:
        await self.sessions.read(actor, session_id=session_id)
        output = await self.agent.aget_run_output(
            run_id, session_id=session_id, user_id=actor.user_id
        )
        if output is None or output.session_id != session_id or output.user_id != actor.user_id:
            raise WorkSessionNotFound("Run does not exist")
        status = getattr(output.status, "value", "UNKNOWN")
        if status in {"COMPLETED", "CANCELLED", "ERROR", "REGENERATED"}:
            return str(status)
        if not await self.agent.acancel_run(run_id):
            raise WorkSessionConflict("Run is not cancellable in this process; reconcile first")
        return "CANCELLING"

    @asynccontextmanager
    async def accept(
        self, actor: ActorContext, session_id: str, run_id: str
    ) -> AsyncIterator[AgentWorkSession]:
        try:
            async with self.engine.connect() as connection:
                await lock_runtime(connection, "careeract_conversation", session_id)
                await connection.commit()
                run_locked = False
                try:
                    await lock_runtime(connection, "careeract_run", run_id)
                    run_locked = True
                    session = await self.sessions.read(actor, session_id=session_id)
                    if session.archived:
                        raise WorkSessionConflict("Restore the conversation first")
                    existing = await asyncio.to_thread(self.agent.db.get_run, run_id)
                    if existing is not None:
                        raise WorkSessionConflict("Request already accepted; read history")
                    if (
                        self.sessions.history is not None
                        and await self.sessions.history.has_active_run(
                            session_id=session_id, user_id=actor.user_id
                        )
                    ):
                        raise WorkSessionConflict("Run outcome must be reconciled first")
                    await connection.commit()
                    yield session
                finally:
                    if run_locked:
                        await unlock_runtime(connection, "careeract_run", run_id)
                    await unlock_runtime(connection, "careeract_conversation", session_id)
        except (DBAPIError, PoolTimeoutError):
            raise WorkSessionUnavailable("Agent execution storage is unavailable") from None
