from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.domain.material import (
    MaterialDetail,
    MaterialDraft,
    MaterialPage,
    MaterialProposal,
    MaterialSource,
)


class MaterialRepository(Protocol):
    async def list(
        self,
        actor: ActorContext,
        *,
        project_id: UUID | None,
        limit: int,
        cursor: str | None,
        scoped: bool = False,
    ) -> MaterialPage: ...

    async def get(self, actor: ActorContext, material_id: UUID) -> MaterialDetail | None: ...

    async def create(
        self,
        actor: ActorContext,
        *,
        material_id: UUID,
        project_id: UUID | None,
        title: str,
        body: str,
        draft: MaterialDraft | None = None,
    ) -> MaterialDetail: ...

    async def create_version(
        self,
        actor: ActorContext,
        *,
        material_id: UUID,
        base_version_id: UUID,
        body: str,
        source: MaterialSource,
    ) -> MaterialDetail | None: ...

    async def create_proposal(
        self,
        actor: ActorContext,
        *,
        material_id: UUID,
        base_version_id: UUID,
        proposed_body: str,
        rationale: str,
        proposal_id: UUID,
        references: tuple[dict[str, str], ...],
    ) -> MaterialProposal | None: ...

    async def resolve_proposal(
        self,
        actor: ActorContext,
        *,
        material_id: UUID,
        proposal_id: UUID,
        state: str,
    ) -> MaterialDetail | None: ...
