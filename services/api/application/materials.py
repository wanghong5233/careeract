from __future__ import annotations

import builtins
import json
from difflib import unified_diff
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from services.api.application.context import ActorContext
from services.api.application.ports.materials import MaterialRepository
from services.api.domain.material import (
    MaterialConflict,
    MaterialDetail,
    MaterialDraft,
    MaterialInvalid,
    MaterialNotFound,
    MaterialPage,
    MaterialProposal,
    validate_material_content,
)
from services.api.domain.privacy import ensure_career_content


class MaterialService:
    def __init__(self, repository: MaterialRepository, *, enabled: bool = False) -> None:
        self.repository = repository
        self.enabled = enabled

    def require_enabled(self) -> None:
        if not self.enabled:
            from services.api.domain.material import MaterialUnavailable

            raise MaterialUnavailable("Synthetic material experiment is disabled")

    async def list(
        self,
        actor: ActorContext,
        *,
        project_id: UUID | None,
        limit: int,
        cursor: str | None = None,
        scoped: bool = False,
    ) -> MaterialPage:
        self.require_enabled()
        if not 1 <= limit <= 50:
            raise MaterialInvalid("Invalid material page size")
        return await self.repository.list(
            actor, project_id=project_id, limit=limit, cursor=cursor, scoped=scoped
        )

    async def read(self, actor: ActorContext, material_id: UUID) -> MaterialDetail:
        self.require_enabled()
        detail = await self.repository.get(actor, material_id)
        if detail is None:
            raise MaterialNotFound("Material does not exist")
        return detail

    async def create(
        self,
        actor: ActorContext,
        *,
        material_id: UUID | None,
        project_id: UUID | None,
        title: str,
        body: str,
        draft: MaterialDraft | None = None,
    ) -> MaterialDetail:
        self.require_enabled()
        title, body = title.strip(), body.strip()
        self.validate(
            title=title,
            body=body if draft is None else draft.body,
            rationale=draft.rationale if draft else None,
        )
        if draft:
            ensure_career_content(draft.references)
            if body:
                raise MaterialInvalid("Agent drafts cannot create an accepted initial version")
        return await self.repository.create(
            actor,
            material_id=material_id or uuid4(),
            project_id=project_id,
            title=title,
            body=body,
            draft=draft,
        )

    async def save_version(
        self,
        actor: ActorContext,
        material_id: UUID,
        *,
        base_version_id: UUID,
        body: str,
    ) -> MaterialDetail:
        self.require_enabled()
        body = body.strip()
        self.validate(body=body)
        detail = await self.repository.create_version(
            actor,
            material_id=material_id,
            base_version_id=base_version_id,
            body=body,
            source="user",
        )
        if detail is None:
            existing = await self.read(actor, material_id)
            if existing.current_version.id != base_version_id:
                raise MaterialConflict("Material changed; reload before saving")
            raise MaterialInvalid("Material version could not be saved")
        return detail

    async def propose(
        self,
        actor: ActorContext,
        material_id: UUID,
        *,
        base_version_id: UUID,
        proposed_body: str,
        rationale: str,
        references: tuple[dict[str, str], ...] = (),
    ) -> MaterialProposal:
        self.require_enabled()
        proposed_body, rationale = proposed_body.strip(), rationale.strip()
        self.validate(body=proposed_body, rationale=rationale)
        ensure_career_content((proposed_body, rationale, references))
        key = json.dumps(
            [
                actor.user_id,
                actor.request_id,
                str(material_id),
                str(base_version_id),
                proposed_body,
                rationale,
                references,
            ],
            ensure_ascii=False,
            sort_keys=True,
        )
        proposal = await self.repository.create_proposal(
            actor,
            material_id=material_id,
            base_version_id=base_version_id,
            proposed_body=proposed_body,
            rationale=rationale,
            proposal_id=uuid5(NAMESPACE_URL, key),
            references=references,
        )
        if proposal is None:
            existing = await self.read(actor, material_id)
            if existing.current_version.id != base_version_id:
                raise MaterialConflict("Material changed; reload before proposing")
            raise MaterialInvalid("Material proposal could not be saved")
        return proposal

    async def resolve(
        self,
        actor: ActorContext,
        material_id: UUID,
        proposal_id: UUID,
        *,
        state: str,
    ) -> MaterialDetail:
        self.require_enabled()
        if state not in {"accepted", "rejected"}:
            raise MaterialInvalid("Unknown proposal state")
        current = await self.read(actor, material_id)
        proposal = next((item for item in current.proposals if item.id == proposal_id), None)
        if proposal is None:
            raise MaterialNotFound("Proposal does not exist")
        if state == "accepted":
            self.validate(body=proposal.proposed_body, rationale=proposal.rationale)
            ensure_career_content(proposal.references)
        detail = await self.repository.resolve_proposal(
            actor, material_id=material_id, proposal_id=proposal_id, state=state
        )
        if detail is None:
            raise MaterialConflict("Proposal is stale or already resolved")
        return detail

    @staticmethod
    def diff(detail: MaterialDetail, proposal: MaterialProposal) -> builtins.list[str]:
        return list(
            unified_diff(
                proposal.base_body.splitlines(),
                proposal.proposed_body.splitlines(),
                fromfile=f"v{proposal.base_number}",
                tofile="提议",
                lineterm="",
            )
        )

    @staticmethod
    def validate(
        *, title: str | None = None, body: str | None = None, rationale: str | None = None
    ) -> None:
        try:
            validate_material_content(title=title, body=body, rationale=rationale)
        except ValueError:
            raise MaterialInvalid("Invalid material content") from None
        ensure_career_content((title, body, rationale))
