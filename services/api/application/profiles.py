from dataclasses import asdict
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.application.ports.profiles import ProfileRepository
from services.api.domain.privacy import ensure_career_content
from services.api.domain.profile import CareerProfile, ProfileContent


class ProfileService:
    def __init__(self, repository: ProfileRepository) -> None:
        self.repository = repository

    async def read(self, actor: ActorContext) -> CareerProfile | None:
        return await self.repository.get(actor)

    async def confirm(
        self,
        actor: ActorContext,
        content: ProfileContent,
        expected_version: UUID | None,
        *,
        confirmed: bool,
    ) -> CareerProfile:
        if not confirmed:
            raise ValueError("The user must confirm the profile before saving")
        ensure_career_content(asdict(content))
        return await self.repository.save_confirmed(actor, content, expected_version)
