import json
from dataclasses import asdict
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.application.context import ActorContext
from services.api.domain.profile import (
    CareerProfile,
    ProfileConflict,
    ProfileContent,
    ProfileUnavailable,
)

CONTENT_ADAPTER = TypeAdapter(ProfileContent)


def profile_from_row(row: RowMapping) -> CareerProfile:
    return CareerProfile(
        user_id=row["user_id"],
        content=CONTENT_ADAPTER.validate_python(row["content"]),
        version=row["version"],
        confirmed_at=row["confirmed_at"],
    )


class PostgresProfileRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def get(self, actor: ActorContext) -> CareerProfile | None:
        try:
            async with self.engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text("SELECT * FROM career.profiles WHERE user_id=:user_id"),
                            {"user_id": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return profile_from_row(row) if row is not None else None
        except (DBAPIError, PoolTimeoutError):
            raise ProfileUnavailable("Profile storage is unavailable") from None

    async def save_confirmed(
        self, actor: ActorContext, content: ProfileContent, expected_version: UUID | None
    ) -> CareerProfile:
        statement = (
            "INSERT INTO career.profiles (user_id, content, version, confirmed_at) "
            "VALUES (:user_id, CAST(:content AS jsonb), :version, clock_timestamp()) "
            "ON CONFLICT (user_id) DO NOTHING RETURNING *"
            if expected_version is None
            else "UPDATE career.profiles SET content=CAST(:content AS jsonb), "
            "version=:version, confirmed_at=clock_timestamp() "
            "WHERE user_id=:user_id AND version=:expected_version RETURNING *"
        )
        try:
            async with self.engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            text(statement),
                            {
                                "user_id": actor.user_id,
                                "content": json.dumps(asdict(content), ensure_ascii=False),
                                "version": uuid4(),
                                "expected_version": expected_version,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ProfileConflict("Profile changed; reload before saving")
                return profile_from_row(row)
        except (DBAPIError, PoolTimeoutError):
            raise ProfileUnavailable("Profile save could not be confirmed") from None
