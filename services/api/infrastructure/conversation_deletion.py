from typing import Any
from uuid import UUID

from agno.exceptions import AgnoError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.application.context import ActorContext
from services.api.application.ports.work_sessions import AgentHistoryReader
from services.api.domain.work_session import (
    WorkSessionConflict,
    WorkSessionNotFound,
    WorkSessionUnavailable,
)
from services.api.infrastructure.agent_execution import lock_conversation


class AgnoConversationDeletion:
    def __init__(self, engine: AsyncEngine, agent: Any, history: AgentHistoryReader) -> None:
        self.engine, self.agent, self.history = engine, agent, history

    async def delete(self, actor: ActorContext, *, session_id: str, expected_version: UUID) -> None:
        try:
            async with self.engine.begin() as connection:
                await lock_conversation(connection, session_id)
                version = await connection.scalar(
                    text(
                        "SELECT version FROM career.agent_work_sessions "
                        "WHERE session_id=:id AND user_id=:user FOR UPDATE"
                    ),
                    {"id": session_id, "user": actor.user_id},
                )
                if version is None:
                    raise WorkSessionNotFound("Conversation does not exist")
                if version != expected_version:
                    raise WorkSessionConflict("Conversation changed; reload before deleting")
                if await self.history.has_active_run(session_id=session_id, user_id=actor.user_id):
                    raise WorkSessionConflict("Stop and reconcile the run before deleting")
                side = await connection.scalar(
                    text(
                        "SELECT session_id FROM career.agent_work_sessions "
                        "WHERE user_id=:user AND side_context->>'source_id'=:id LIMIT 1"
                    ),
                    {"id": session_id, "user": actor.user_id},
                )
                if side:
                    raise WorkSessionConflict("Close the related temporary chat before deleting")
                await self.agent.adelete_session(session_id=session_id, user_id=actor.user_id)
                remaining = await self.agent.aget_session(
                    session_id=session_id, user_id=actor.user_id
                )
                if remaining is not None:
                    raise WorkSessionUnavailable("Framework history deletion is unconfirmed")
                await connection.execute(
                    text(
                        "DELETE FROM career.agent_work_sessions "
                        "WHERE session_id=:id AND user_id=:user"
                    ),
                    {"id": session_id, "user": actor.user_id},
                )
        except (AgnoError, DBAPIError, PoolTimeoutError, ValueError, TypeError):
            raise WorkSessionUnavailable(
                "Conversation deletion is unconfirmed; reload before retrying"
            ) from None
