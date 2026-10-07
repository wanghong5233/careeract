from uuid import UUID, uuid4

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.application.context import ActorContext
from services.api.domain.boss_connection import (
    ACTIVE_BOSS_CONNECTION_STATUSES,
    BossConnection,
    BossConnectionConflict,
    BossConnectionUnavailable,
)


def connection_from_row(row: RowMapping) -> BossConnection:
    return BossConnection(
        id=row["id"],
        user_id=row["user_id"],
        platform=row["platform"],
        request_key=row["request_key"],
        version=row["version"],
        browser_session_id=row["browser_session_id"],
        status=row["status"],
        last_observed_url=row["last_observed_url"],
        last_observed_state=row["last_observed_state"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresBossConnectionRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def get_current(self, actor: ActorContext) -> BossConnection | None:
        try:
            async with self.engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM career.boss_connections "
                                "WHERE user_id=:user_id ORDER BY created_at DESC,id DESC LIMIT 1"
                            ),
                            {"user_id": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return connection_from_row(row) if row is not None else None
        except (DBAPIError, PoolTimeoutError):
            raise BossConnectionUnavailable("BOSS connection storage is unavailable") from None

    async def start(
        self, actor: ActorContext, *, connection_id: UUID, request_key: UUID
    ) -> BossConnection:
        try:
            async with self.engine.begin() as connection:
                await connection.execute(
                    text('SELECT id FROM auth."user" WHERE id=:user_id FOR UPDATE'),
                    {"user_id": actor.user_id},
                )
                current = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM career.boss_connections "
                                "WHERE user_id=:user_id AND "
                                "(request_key=:request_key OR status NOT IN ('revoked','failed')) "
                                "ORDER BY (request_key=:request_key) DESC LIMIT 1 FOR UPDATE"
                            ),
                            {"user_id": actor.user_id, "request_key": request_key},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if current is not None and current["request_key"] == request_key:
                    return connection_from_row(current)
                if current is not None and current["status"] in ACTIVE_BOSS_CONNECTION_STATUSES:
                    raise BossConnectionConflict("An active connection request already exists")
                row = (
                    (
                        await connection.execute(
                            text(
                                "INSERT INTO career.boss_connections "
                                "(id,user_id,platform,request_key,version,status,"
                                "last_observed_state,created_at,updated_at) "
                                "VALUES (:id,:user_id,'boss',:request_key,:version,'pending',"
                                "'browser_session_not_started',clock_timestamp(),"
                                "clock_timestamp()) RETURNING *"
                            ),
                            {
                                "id": connection_id,
                                "user_id": actor.user_id,
                                "request_key": request_key,
                                "version": uuid4(),
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                return connection_from_row(row)
        except (DBAPIError, PoolTimeoutError):
            raise BossConnectionUnavailable("BOSS connection could not be started") from None

    async def revoke(
        self, actor: ActorContext, connection_id: UUID, *, expected_version: UUID
    ) -> BossConnection | None:
        try:
            async with self.engine.begin() as connection:
                current = (
                    (
                        await connection.execute(
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
                if current is None:
                    return None
                if current["status"] == "revoked":
                    return connection_from_row(current)
                if (
                    current["version"] != expected_version
                    or current["browser_session_id"] is not None
                ):
                    raise BossConnectionConflict("Connection requires reconciliation before revoke")
                row = (
                    (
                        await connection.execute(
                            text(
                                "UPDATE career.boss_connections SET status='revoked', "
                                "last_observed_state='revoked_by_user', "
                                "version=:version, updated_at=clock_timestamp() "
                                "WHERE id=:id AND user_id=:user_id RETURNING *"
                            ),
                            {"id": connection_id, "user_id": actor.user_id, "version": uuid4()},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return connection_from_row(row) if row is not None else None
        except (DBAPIError, PoolTimeoutError):
            raise BossConnectionUnavailable("BOSS connection could not be revoked") from None
