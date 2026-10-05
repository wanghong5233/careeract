import base64
import binascii
import json
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.application.context import ActorContext
from services.api.application.ports.work_sessions import AgentHistoryReader, WorkSessionPage
from services.api.domain.work_session import (
    AgentWorkSession,
    WorkSessionConflict,
    WorkSessionInvalid,
    WorkSessionNotFound,
    WorkSessionUnavailable,
)


def work_session_from_row(row: RowMapping) -> AgentWorkSession:
    return AgentWorkSession(
        session_id=row["session_id"],
        user_id=row["user_id"],
        project_id=row["project_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        title=row["title"],
        archived=row["archived"],
        version=row["version"],
        context_version=row["context_version"],
        title_origin=row["title_origin"],
        title_generation_attempted=row["title_generation_attempted"],
        model_id=row["model_id"],
    )


def encode_cursor(session: AgentWorkSession) -> str:
    payload = json.dumps([session.created_at.isoformat(), session.session_id])
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        if not 1 <= len(cursor) <= 512:
            raise ValueError
        value = json.loads(
            base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        )
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(isinstance(item, str) for item in value)
        ):
            raise ValueError
        created_at = datetime.fromisoformat(value[0])
        if created_at.utcoffset() is None or not value[1]:
            raise ValueError
        return created_at, value[1]
    except (ValueError, binascii.Error):
        raise WorkSessionInvalid("Invalid conversation cursor") from None


class PostgresAgentWorkSessionRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.history: AgentHistoryReader | None = None

    async def claim_title(
        self, actor: ActorContext, *, session_id: str, expected_version: UUID, retry: bool = False
    ) -> AgentWorkSession | None:
        return await self._title_write(
            actor,
            session_id,
            expected_version,
            "title_generation_attempted=true",
            "title_origin='default'" + ("" if retry else " AND NOT title_generation_attempted"),
        )

    async def save_generated_title(
        self, actor: ActorContext, *, session_id: str, title: str, expected_version: UUID
    ) -> AgentWorkSession | None:
        return await self._title_write(
            actor,
            session_id,
            expected_version,
            "title=:title, title_origin='generated'",
            "title_origin='default' AND title_generation_attempted",
            title,
        )

    async def _title_write(
        self,
        actor: ActorContext,
        session_id: str,
        expected_version: UUID,
        assignments: str,
        condition: str,
        title: str | None = None,
    ) -> AgentWorkSession | None:
        try:
            async with self.engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                f"UPDATE career.agent_work_sessions SET {assignments}, "
                                "version=:version, updated_at=clock_timestamp() "
                                "WHERE session_id=:session_id AND user_id=:user_id "
                                f"AND version=:expected_version AND {condition} RETURNING *"
                            ),
                            {
                                "session_id": session_id,
                                "user_id": actor.user_id,
                                "expected_version": expected_version,
                                "version": uuid4(),
                                "title": title,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return work_session_from_row(row) if row else None
        except (DBAPIError, PoolTimeoutError):
            raise WorkSessionUnavailable("Conversation title could not be saved") from None

    async def list(
        self, actor: ActorContext, *, cursor: str | None, limit: int, archived: bool | None
    ) -> WorkSessionPage:
        boundary = decode_cursor(cursor) if cursor else None
        parameters: dict[str, object] = {"user_id": actor.user_id, "limit": limit + 1}
        condition = ""
        if boundary:
            parameters.update({"created_at": boundary[0], "session_id": boundary[1]})
            condition += " AND (created_at, session_id) < (:created_at, :session_id)"
        if archived is not None:
            parameters["archived"] = archived
            condition += " AND archived=:archived"
        try:
            async with self.engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM career.agent_work_sessions WHERE user_id=:user_id"
                                + condition
                                + " ORDER BY created_at DESC, session_id DESC LIMIT :limit"
                            ),
                            parameters,
                        )
                    )
                    .mappings()
                    .all()
                )
            items = tuple(work_session_from_row(row) for row in rows[:limit])
            return WorkSessionPage(items, encode_cursor(items[-1]) if len(rows) > limit else None)
        except (DBAPIError, PoolTimeoutError):
            raise WorkSessionUnavailable("Conversation directory is unavailable") from None

    async def create(
        self,
        actor: ActorContext,
        *,
        session_id: str,
        title: str,
        project_id: UUID | None,
        model_id: str | None = None,
    ) -> AgentWorkSession:
        try:
            async with self.engine.begin() as connection:
                if project_id is not None:
                    project = await connection.scalar(
                        text(
                            "SELECT id FROM career.career_projects "
                            "WHERE id=:id AND user_id=:user_id FOR KEY SHARE"
                        ),
                        {"id": project_id, "user_id": actor.user_id},
                    )
                    if project is None:
                        raise WorkSessionNotFound("Project does not exist")
                parameters = {
                    "session_id": session_id,
                    "user_id": actor.user_id,
                    "title": title,
                    "project_id": project_id,
                    "title_origin": "default" if title == "新对话" else "manual",
                    "model_id": model_id,
                }
                row = (
                    (
                        await connection.execute(
                            text(
                                "INSERT INTO career.agent_work_sessions "
                                "(session_id, user_id, title, project_id, title_origin, model_id) "
                                "VALUES (:session_id, :user_id, :title, :project_id, "
                                ":title_origin, :model_id) "
                                "ON CONFLICT (session_id) DO NOTHING RETURNING *"
                            ),
                            parameters,
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    row = (
                        (
                            await connection.execute(
                                text(
                                    "SELECT * FROM career.agent_work_sessions "
                                    "WHERE session_id=:session_id AND user_id=:user_id"
                                ),
                                parameters,
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if row is None or (row["title"], row["project_id"], row["archived"]) != (
                        title,
                        project_id,
                        False,
                    ):
                        raise WorkSessionConflict("Create ID already used; read before changing")
                return work_session_from_row(row)
        except (DBAPIError, PoolTimeoutError):
            raise WorkSessionUnavailable("Conversation could not be created") from None

    async def update(
        self,
        actor: ActorContext,
        *,
        session_id: str,
        title: str | None,
        archived: bool | None,
        project_id: UUID | None,
        change_project: bool,
        expected_version: UUID,
        model_id: str | None = None,
    ) -> AgentWorkSession | None:
        try:
            async with self.engine.begin() as connection:
                if change_project or archived is not None or model_id is not None:
                    from services.api.infrastructure.agent_execution import lock_conversation

                    await lock_conversation(connection, session_id)
                    if self.history is not None and await self.history.has_active_run(
                        session_id=session_id, user_id=actor.user_id
                    ):
                        raise WorkSessionConflict("Wait for the active run to end")
                if change_project and project_id is not None:
                    project = await connection.scalar(
                        text(
                            "SELECT id FROM career.career_projects "
                            "WHERE id=:id AND user_id=:user_id FOR KEY SHARE"
                        ),
                        {"id": project_id, "user_id": actor.user_id},
                    )
                    if project is None:
                        raise WorkSessionNotFound("Project does not exist")
                row = (
                    (
                        await connection.execute(
                            text(
                                "UPDATE career.agent_work_sessions SET "
                                "title=COALESCE(:title, title), "
                                "title_origin=CASE WHEN CAST(:title AS TEXT) IS NOT NULL "
                                "THEN 'manual' ELSE title_origin END, "
                                "archived=COALESCE(:archived, archived), "
                                "model_id=COALESCE(:model_id, model_id), "
                                "project_id=CASE WHEN :change_project THEN :project_id "
                                "ELSE project_id END, "
                                "context_version=CASE WHEN :change_project "
                                "AND project_id IS DISTINCT FROM :project_id "
                                "THEN gen_random_uuid() ELSE context_version END, "
                                "version=:version, updated_at=clock_timestamp() "
                                "WHERE session_id=:session_id AND user_id=:user_id "
                                "AND version=:expected_version RETURNING *"
                            ),
                            {
                                "session_id": session_id,
                                "user_id": actor.user_id,
                                "title": title,
                                "archived": archived,
                                "model_id": model_id,
                                "project_id": project_id,
                                "change_project": change_project,
                                "version": uuid4(),
                                "expected_version": expected_version,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return work_session_from_row(row) if row else None
        except (DBAPIError, PoolTimeoutError):
            raise WorkSessionUnavailable("Conversation could not be saved") from None

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
                from services.api.infrastructure.agent_execution import lock_conversation

                await lock_conversation(connection, session_id)
                if self.history is not None and await self.history.has_active_run(
                    session_id=session_id, user_id=actor.user_id
                ):
                    raise WorkSessionConflict("Wait for the active run to end")
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
                                "project_id=:project_id, version=gen_random_uuid(), "
                                "context_version=CASE WHEN career.agent_work_sessions.project_id "
                                "IS DISTINCT FROM :project_id "
                                "THEN gen_random_uuid() ELSE "
                                "career.agent_work_sessions.context_version END, "
                                "updated_at=clock_timestamp() "
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
