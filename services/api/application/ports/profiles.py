from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.domain.profile import CareerProfile, ProfileContent


class ProfileRepository(Protocol):
    async def get(self, actor: ActorContext) -> CareerProfile | None: ...

    async def save_confirmed(
        self, actor: ActorContext, content: ProfileContent, expected_version: UUID | None
    ) -> CareerProfile: ...
