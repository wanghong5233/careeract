from uuid import UUID, uuid4

from services.api.application.context import ActorContext
from services.api.application.ports.boss_connections import BossConnectionRepository
from services.api.domain.boss_connection import (
    BossConnection,
    BossConnectionNotFound,
)


class BossConnectionService:
    def __init__(self, repository: BossConnectionRepository) -> None:
        self.repository = repository

    async def read(self, actor: ActorContext) -> BossConnection | None:
        return await self.repository.get_current(actor)

    async def start(self, actor: ActorContext, *, request_key: UUID) -> BossConnection:
        return await self.repository.start(actor, connection_id=uuid4(), request_key=request_key)

    async def revoke(
        self, actor: ActorContext, connection_id: UUID, *, expected_version: UUID
    ) -> BossConnection:
        connection = await self.repository.revoke(
            actor, connection_id, expected_version=expected_version
        )
        if connection is None:
            raise BossConnectionNotFound("BOSS connection does not exist")
        return connection
