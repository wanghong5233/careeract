import base64
import binascii
import json
import re
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.application.context import ActorContext
from services.api.application.ports.projects import ProjectPage
from services.api.domain.project import (
    CareerProject,
    ProjectConflict,
    ProjectInvalid,
    ProjectStatus,
    ProjectUnavailable,
)


def encode_cursor(updated_at: datetime, project_id: UUID) -> str:
    payload = json.dumps({"updated_at": updated_at.isoformat(), "id": str(project_id)})
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        if not 1 <= len(cursor) <= 512 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
            raise ValueError
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.b64decode(cursor + padding, altchars=b"-_", validate=True))
        if (
            not isinstance(payload, dict)
            or set(payload) != {"updated_at", "id"}
            or not isinstance(payload["updated_at"], str)
            or not isinstance(payload["id"], str)
        ):
            raise ValueError
        updated_at = datetime.fromisoformat(payload["updated_at"])
        if updated_at.utcoffset() is None:
            raise ValueError
        return updated_at, UUID(payload["id"])
    except (ValueError, binascii.Error):
        raise ProjectInvalid("Invalid project cursor") from None


def project_from_row(row: RowMapping) -> CareerProject:
    return CareerProject(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        purpose=row["purpose"],
        status=row["status"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresProjectRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def list(
        self, actor: ActorContext, *, cursor: str | None, limit: int, archived: bool | None
    ) -> ProjectPage:
        boundary = decode_cursor(cursor) if cursor is not None else None
        try:
            async with self.engine.connect() as connection:
                parameters: dict[str, object] = {"user_id": actor.user_id, "limit": limit + 1}
                condition = ""
                if boundary is not None:
                    updated_at, project_id = boundary
                    parameters.update({"cursor_updated_at": updated_at, "cursor_id": project_id})
                    condition = "AND (updated_at, id) < (:cursor_updated_at, :cursor_id)"
                if archived is not None:
                    parameters["archived"] = archived
                    condition += " AND (status = 'archived') = :archived"
                rows = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM career.career_projects "
                                "WHERE user_id=:user_id "
                                + condition
                                + " ORDER BY updated_at DESC, id DESC LIMIT :limit"
                            ),
                            parameters,
                        )
                    )
                    .mappings()
                    .all()
                )
                projects = [project_from_row(row) for row in rows]
                next_cursor = None
                if len(projects) > limit:
                    last = projects[limit - 1]
                    next_cursor = encode_cursor(last.updated_at, last.id)
                    projects = projects[:limit]
                return ProjectPage(tuple(projects), next_cursor)
        except (DBAPIError, PoolTimeoutError):
            raise ProjectUnavailable("Project storage is unavailable") from None

    async def get(self, actor: ActorContext, project_id: UUID) -> CareerProject | None:
        try:
            async with self.engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM career.career_projects "
                                "WHERE user_id=:user_id AND id=:id"
                            ),
                            {"user_id": actor.user_id, "id": project_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return project_from_row(row) if row is not None else None
        except (DBAPIError, PoolTimeoutError):
            raise ProjectUnavailable("Project storage is unavailable") from None

    async def create(
        self,
        actor: ActorContext,
        *,
        project_id: UUID,
        title: str,
        purpose: str,
        status: ProjectStatus,
    ) -> CareerProject:
        version = uuid4()
        try:
            async with self.engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "INSERT INTO career.career_projects "
                                "(id, user_id, title, purpose, status, version) "
                                "VALUES (:id, :user_id, :title, :purpose, :status, :version) "
                                "ON CONFLICT (id) DO NOTHING RETURNING *"
                            ),
                            {
                                "id": project_id,
                                "user_id": actor.user_id,
                                "title": title,
                                "purpose": purpose,
                                "status": status,
                                "version": version,
                            },
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
                                    "SELECT * FROM career.career_projects "
                                    "WHERE id=:id AND user_id=:user_id"
                                ),
                                {"id": project_id, "user_id": actor.user_id},
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if row is None or (row["title"], row["purpose"], row["status"]) != (
                        title,
                        purpose,
                        status,
                    ):
                        raise ProjectConflict("Project ID already in use; read before changing")
                return project_from_row(row)
        except (DBAPIError, PoolTimeoutError):
            raise ProjectUnavailable("Project could not be saved") from None

    async def update(
        self,
        actor: ActorContext,
        project_id: UUID,
        *,
        title: str | None,
        purpose: str | None,
        status: ProjectStatus | None,
        expected_version: UUID,
    ) -> CareerProject | None:
        try:
            async with self.engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "UPDATE career.career_projects SET "
                                "title=COALESCE(:title, title), "
                                "purpose=COALESCE(:purpose, purpose), "
                                "status=COALESCE(:status, status), "
                                "version=:version, updated_at=clock_timestamp() "
                                "WHERE id=:id AND user_id=:user_id AND version=:expected_version "
                                "RETURNING *"
                            ),
                            {
                                "id": project_id,
                                "user_id": actor.user_id,
                                "title": title,
                                "purpose": purpose,
                                "status": status,
                                "version": uuid4(),
                                "expected_version": expected_version,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return project_from_row(row) if row is not None else None
        except (DBAPIError, PoolTimeoutError):
            raise ProjectUnavailable("Project could not be saved") from None
