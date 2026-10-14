from datetime import datetime
from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.application.context import ActorContext
from services.api.application.ports.boss_saved_login_viewer import (
    BossSavedLoginViewerRepository,
)
from services.api.application.ports.browser_control import BrowserControlContext
from services.api.domain.boss_saved_login_viewer import (
    BossSavedLoginViewer,
    SavedLoginViewerConflict,
    SavedLoginViewerUnavailable,
)


def viewer_from_row(row: RowMapping) -> BossSavedLoginViewer:
    return BossSavedLoginViewer(
        id=row["id"],
        user_id=row["user_id"],
        connection_id=row["connection_id"],
        browser_session_id=row["browser_session_id"],
        version=row["version"],
        status=row["status"],
        expires_at=row["expires_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresBossSavedLoginViewerRepository(BossSavedLoginViewerRepository):
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def read(self, actor: ActorContext, connection_id: UUID) -> BossSavedLoginViewer | None:
        try:
            async with self.engine.connect() as database:
                row = (
                    (
                        await database.execute(
                            text(
                                "SELECT * FROM career.boss_saved_login_viewers "
                                "WHERE connection_id=:connection AND user_id=:user "
                                "AND status IN ('starting','live','closing') "
                                "ORDER BY created_at DESC LIMIT 1"
                            ),
                            {"connection": connection_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return viewer_from_row(row) if row is not None else None
        except (DBAPIError, PoolTimeoutError):
            raise SavedLoginViewerUnavailable("Saved login viewer storage is unavailable") from None

    async def reserve(
        self,
        actor: ActorContext,
        connection_id: UUID,
        *,
        expected_connection_version: UUID,
        viewer_id: UUID,
        browser_session_id: UUID,
        expires_at: datetime,
    ) -> BossSavedLoginViewer:
        try:
            async with self.engine.begin() as database:
                connection = (
                    (
                        await database.execute(
                            text(
                                "SELECT * FROM career.boss_connections "
                                "WHERE id=:connection AND user_id=:user FOR UPDATE"
                            ),
                            {"connection": connection_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if connection is None:
                    from services.api.domain.boss_connection import BossConnectionNotFound

                    raise BossConnectionNotFound("BOSS connection does not exist")
                if (
                    connection["status"] != "connected"
                    or connection["version"] != expected_connection_version
                    or connection["browser_session_id"] is None
                ):
                    raise SavedLoginViewerConflict("Saved login is not available")
                existing = (
                    (
                        await database.execute(
                            text(
                                "SELECT * FROM career.boss_saved_login_viewers "
                                "WHERE connection_id=:connection AND user_id=:user "
                                "AND status IN ('starting','live','closing') FOR UPDATE"
                            ),
                            {"connection": connection_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing is not None:
                    return viewer_from_row(existing)
                sending = await database.scalar(
                    text(
                        "SELECT 1 FROM career.execution_resources r "
                        "JOIN career.execution_tasks t ON t.id=r.task_id "
                        "JOIN career.communication_sends s ON s.task_id=t.id "
                        "WHERE r.connection_id=:id AND r.user_id=:user "
                        "AND (t.status IN ('accepted','running','unknown') OR s.cleanup_required)"
                    ),
                    {"id": connection_id, "user": actor.user_id},
                )
                if sending:
                    raise SavedLoginViewerConflict("Finish the current send before manual control")
                row = (
                    (
                        await database.execute(
                            text(
                                "INSERT INTO career.boss_saved_login_viewers "
                                "(id,user_id,connection_id,browser_session_id,version,status,"
                                "expires_at) "
                                "VALUES (:id,:user,:connection,:session,:version,'starting',"
                                ":expires) "
                                "RETURNING *"
                            ),
                            {
                                "id": viewer_id,
                                "user": actor.user_id,
                                "connection": connection_id,
                                "session": browser_session_id,
                                "version": UUID(actor.request_id),
                                "expires": expires_at,
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                return viewer_from_row(row)
        except IntegrityError:
            raise SavedLoginViewerConflict("Saved login viewer already exists") from None
        except (DBAPIError, PoolTimeoutError):
            raise SavedLoginViewerUnavailable("Saved login viewer storage is unavailable") from None

    async def context(self, actor: ActorContext, viewer_id: UUID) -> BrowserControlContext | None:
        try:
            async with self.engine.connect() as database:
                row = (
                    (
                        await database.execute(
                            text(
                                "SELECT id, user_id, browser_session_id, expires_at "
                                "FROM career.boss_saved_login_viewers "
                                "WHERE id=:id AND user_id=:user "
                                "AND status IN ('starting','live','closing')"
                            ),
                            {"id": viewer_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return None
                return BrowserControlContext(
                    actor.user_id,
                    row["browser_session_id"],
                    row["id"],
                    row["id"],
                    row["expires_at"],
                    row["id"],
                    UUID(actor.request_id),
                    "saved-login-viewer",
                )
        except (DBAPIError, PoolTimeoutError):
            raise SavedLoginViewerUnavailable("Saved login viewer storage is unavailable") from None

    async def mark_live(self, actor: ActorContext, viewer_id: UUID) -> BossSavedLoginViewer:
        return await self._transition(actor, viewer_id, "starting", "live")

    async def begin_close(
        self,
        actor: ActorContext,
        connection_id: UUID,
        *,
        expected_connection_version: UUID,
    ) -> BrowserControlContext | None:
        try:
            async with self.engine.begin() as database:
                row = (
                    (
                        await database.execute(
                            text(
                                "SELECT v.*, c.version AS connection_version "
                                "FROM career.boss_saved_login_viewers v "
                                "JOIN career.boss_connections c ON c.id=v.connection_id "
                                "AND c.user_id=v.user_id "
                                "WHERE v.connection_id=:connection AND v.user_id=:user "
                                "AND v.status IN ('starting','live','closing') FOR UPDATE"
                            ),
                            {"connection": connection_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return None
                if row["connection_version"] != expected_connection_version:
                    raise SavedLoginViewerConflict("BOSS connection has changed")
                if row["status"] != "closing":
                    await database.execute(
                        text(
                            "UPDATE career.boss_saved_login_viewers SET status='closing', "
                            "updated_at=clock_timestamp() WHERE id=:id"
                        ),
                        {"id": row["id"]},
                    )
                return BrowserControlContext(
                    actor.user_id,
                    row["browser_session_id"],
                    row["id"],
                    row["id"],
                    row["expires_at"],
                    row["id"],
                    UUID(actor.request_id),
                    "saved-login-viewer",
                )
        except (DBAPIError, PoolTimeoutError):
            raise SavedLoginViewerUnavailable("Saved login viewer storage is unavailable") from None

    async def mark_released(self, actor: ActorContext, viewer_id: UUID) -> BossSavedLoginViewer:
        return await self._transition(actor, viewer_id, "closing", "released")

    async def mark_failed(self, actor: ActorContext, viewer_id: UUID) -> BossSavedLoginViewer:
        return await self._transition(actor, viewer_id, "starting", "failed")

    async def _transition(
        self, actor: ActorContext, viewer_id: UUID, expected: str, status: str
    ) -> BossSavedLoginViewer:
        try:
            async with self.engine.begin() as database:
                row = (
                    (
                        await database.execute(
                            text(
                                "UPDATE career.boss_saved_login_viewers SET status=:status, "
                                "updated_at=clock_timestamp() WHERE id=:id AND user_id=:user "
                                "AND status=:expected RETURNING *"
                            ),
                            {
                                "id": viewer_id,
                                "user": actor.user_id,
                                "expected": expected,
                                "status": status,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise SavedLoginViewerConflict("Saved login viewer state changed")
                return viewer_from_row(row)
        except (DBAPIError, PoolTimeoutError):
            raise SavedLoginViewerUnavailable("Saved login viewer storage is unavailable") from None
