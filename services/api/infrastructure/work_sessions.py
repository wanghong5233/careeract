from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.application.context import ActorContext
from services.api.domain.work_session import (
    AgentWorkSession,
    WorkSessionUnavailable,
)


def work_session_from_row(row: RowMapping) -> AgentWorkSession:
    return AgentWorkSession(
        session_id=row["session_id"],
        user_id=row["user_id"],
        project_id=row["project_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresAgentWorkSessionRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def get(self, actor: ActorContext, session_id: str) -> AgentWorkSession | None:
        try:
            async with self.engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM career.agent_work_sessions "
                                "WHERE session_id=:session_id AND user_id=:user_id"
                            ),
                            {"session_id": session_id, "user_id": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return work_session_from_row(row) if row is not None else None
        except (DBAPIError, PoolTimeoutError):
            raise WorkSessionUnavailable("Agent work session storage is unavailable") from None

    async def associate(
        self, actor: ActorContext, *, session_id: str, project_id: UUID | None
    ) -> AgentWorkSession | None:
        try:
            async with self.engine.begin() as connection:
                if project_id is not None:
                    project_exists = await connection.scalar(
                        text(
                            "SELECT 1 FROM career.career_projects "
                            "WHERE id=:project_id AND user_id=:user_id"
                        ),
                        {"project_id": project_id, "user_id": actor.user_id},
                    )
                    if project_exists is None:
                        return None
                row = (
                    (
                        await connection.execute(
                            text(
                                "INSERT INTO career.agent_work_sessions "
                                "(session_id, user_id, project_id) "
                                "VALUES (:session_id, :user_id, :project_id) "
                                "ON CONFLICT (session_id) DO UPDATE SET "
                                "project_id=:project_id, updated_at=clock_timestamp() "
                                "WHERE career.agent_work_sessions.user_id=:user_id "
                                "RETURNING *"
                            ),
                            {
                                "session_id": session_id,
                                "user_id": actor.user_id,
                                "project_id": project_id,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return work_session_from_row(row) if row is not None else None
        except (DBAPIError, PoolTimeoutError):
            raise WorkSessionUnavailable("Agent work session could not be saved") from None
