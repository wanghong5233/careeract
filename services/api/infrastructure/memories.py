import base64
import binascii
import json
import re
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from services.api.application.context import ActorContext
from services.api.domain.memory import (
    MemoryConflict,
    MemoryInvalid,
    MemoryKind,
    MemoryNotFound,
    MemoryPage,
    MemoryUnavailable,
    WorkspaceMemory,
)


def encode_cursor(updated_at: datetime, memory_id: UUID) -> str:
    payload = json.dumps({"updated_at": updated_at.isoformat(), "id": str(memory_id)})
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
        raise MemoryInvalid("Invalid memory cursor") from None


def memory_from_row(row: RowMapping) -> WorkspaceMemory:
    return WorkspaceMemory(
        id=row["id"],
        user_id=row["user_id"],
        project_id=row["project_id"],
        kind=row["kind"],
        state=row["state"],
        title=row["title"],
        content=row["content"],
        source=row["source"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def ensure_owned_project(
    connection: AsyncConnection, actor: ActorContext, project_id: UUID | None
) -> None:
    if project_id is None:
        return
    owned = await connection.scalar(
        text(
            "SELECT 1 FROM career.career_projects WHERE id=:id AND user_id=:user_id FOR KEY SHARE"
        ),
        {"id": project_id, "user_id": actor.user_id},
    )
    if owned is None:
        raise MemoryNotFound("Memory or related project does not exist")


class PostgresMemoryRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def effective_rules(
        self, actor: ActorContext, *, project_id: UUID | None, limit: int
    ) -> tuple[WorkspaceMemory, ...]:
        try:
            async with self.engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM career.workspace_memories "
                                "WHERE user_id=:user_id AND kind='rule' AND state='confirmed' "
                                "AND (project_id IS NULL OR project_id=:project_id) "
                                "ORDER BY updated_at DESC, id DESC LIMIT :limit"
                            ),
                            {"user_id": actor.user_id, "project_id": project_id, "limit": limit},
                        )
                    )
                    .mappings()
                    .all()
                )
                return tuple(memory_from_row(row) for row in rows)
        except (DBAPIError, PoolTimeoutError):
            raise MemoryUnavailable("Effective rules are unavailable") from None

    async def list(
        self,
        actor: ActorContext,
        *,
        cursor: str | None,
        limit: int,
        kind: MemoryKind | None,
        include_retired: bool,
    ) -> MemoryPage:
        boundary = decode_cursor(cursor) if cursor is not None else None
        try:
            async with self.engine.connect() as connection:
                parameters: dict[str, object] = {"user_id": actor.user_id, "limit": limit + 1}
                conditions = ["user_id=:user_id"]
                if boundary is not None:
                    updated_at, memory_id = boundary
                    parameters.update({"cursor_updated_at": updated_at, "cursor_id": memory_id})
                    conditions.append("(updated_at, id) < (:cursor_updated_at, :cursor_id)")
                if kind is not None:
                    parameters["kind"] = kind
                    conditions.append("kind=:kind")
                if not include_retired:
                    conditions.append("state <> 'retired'")
                rows = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM career.workspace_memories WHERE "
                                + " AND ".join(conditions)
                                + " ORDER BY updated_at DESC, id DESC LIMIT :limit"
                            ),
                            parameters,
                        )
                    )
                    .mappings()
                    .all()
                )
                items = [memory_from_row(row) for row in rows]
                next_cursor = None
                if len(items) > limit:
                    last = items[limit - 1]
                    next_cursor = encode_cursor(last.updated_at, last.id)
                    items = items[:limit]
                return MemoryPage(tuple(items), next_cursor)
        except (DBAPIError, PoolTimeoutError):
            raise MemoryUnavailable("Memory storage is unavailable") from None

    async def get(self, actor: ActorContext, memory_id: UUID) -> WorkspaceMemory | None:
        try:
            async with self.engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM career.workspace_memories "
                                "WHERE id=:id AND user_id=:user_id"
                            ),
                            {"id": memory_id, "user_id": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return memory_from_row(row) if row is not None else None
        except (DBAPIError, PoolTimeoutError):
            raise MemoryUnavailable("Memory storage is unavailable") from None

    async def create(
        self,
        actor: ActorContext,
        *,
        memory_id: UUID,
        project_id: UUID | None,
        kind: MemoryKind,
        title: str,
        content: str,
        source: str,
    ) -> WorkspaceMemory:
        version = uuid4()
        try:
            async with self.engine.begin() as connection:
                await ensure_owned_project(connection, actor, project_id)
                row = (
                    (
                        await connection.execute(
                            text(
                                "INSERT INTO career.workspace_memories "
                                "(id, user_id, project_id, kind, state, title, content, "
                                "source, version) "
                                "VALUES (:id, :user_id, :project_id, :kind, 'candidate', "
                                ":title, :content, :source, :version) "
                                "ON CONFLICT (id) DO NOTHING RETURNING *"
                            ),
                            {
                                "id": memory_id,
                                "user_id": actor.user_id,
                                "project_id": project_id,
                                "kind": kind,
                                "title": title,
                                "content": content,
                                "source": source,
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
                                    "SELECT * FROM career.workspace_memories "
                                    "WHERE id=:id AND user_id=:user_id"
                                ),
                                {"id": memory_id, "user_id": actor.user_id},
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if (
                        row is None
                        or row["state"] == "retired"
                        or (
                            row["title"],
                            row["content"],
                            row["kind"],
                            row["source"],
                            row["project_id"],
                        )
                        != (
                            title,
                            content,
                            kind,
                            source,
                            project_id,
                        )
                    ):
                        raise MemoryConflict("Memory ID already belongs to another record")
                return memory_from_row(row)
        except (DBAPIError, PoolTimeoutError):
            raise MemoryUnavailable("Memory could not be saved") from None

    async def update(
        self,
        actor: ActorContext,
        memory_id: UUID,
        *,
        project_id: UUID | None,
        title: str | None,
        content: str | None,
        expected_version: UUID,
    ) -> WorkspaceMemory | None:
        try:
            async with self.engine.begin() as connection:
                await ensure_owned_project(connection, actor, project_id)
                row = (
                    (
                        await connection.execute(
                            text(
                                "UPDATE career.workspace_memories SET "
                                "state=CASE WHEN kind='rule' THEN 'candidate' ELSE state END, "
                                "project_id=COALESCE(:project_id, project_id), "
                                "title=COALESCE(:title, title), "
                                "content=COALESCE(:content, content), "
                                "version=:version, updated_at=clock_timestamp() "
                                "WHERE id=:id AND user_id=:user_id AND state <> 'retired' "
                                "AND version=:expected_version RETURNING *"
                            ),
                            {
                                "id": memory_id,
                                "user_id": actor.user_id,
                                "project_id": project_id,
                                "title": title,
                                "content": content,
                                "version": uuid4(),
                                "expected_version": expected_version,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return memory_from_row(row) if row is not None else None
        except (DBAPIError, PoolTimeoutError):
            raise MemoryUnavailable("Memory could not be saved") from None

    async def transition(
        self,
        actor: ActorContext,
        memory_id: UUID,
        *,
        state: str,
        expected_version: UUID,
    ) -> WorkspaceMemory | None:
        try:
            async with self.engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "UPDATE career.workspace_memories SET state=:state, "
                                "version=:version, "
                                "updated_at=clock_timestamp() WHERE id=:id AND user_id=:user_id "
                                "AND state <> 'retired' AND version=:expected_version RETURNING *"
                            ),
                            {
                                "id": memory_id,
                                "user_id": actor.user_id,
                                "state": state,
                                "version": uuid4(),
                                "expected_version": expected_version,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return memory_from_row(row) if row is not None else None
        except (DBAPIError, PoolTimeoutError):
            raise MemoryUnavailable("Memory transition could not be saved") from None
