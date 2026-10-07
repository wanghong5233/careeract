from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.domain.boss_connection import BossConnection


class BossConnectionRepository(Protocol):
    async def get_current(self, actor: ActorContext) -> BossConnection | None: ...

    async def start(
        self, actor: ActorContext, *, connection_id: UUID, request_key: UUID
    ) -> BossConnection: ...

    async def revoke(
        self, actor: ActorContext, connection_id: UUID, *, expected_version: UUID
    ) -> BossConnection | None: ...
