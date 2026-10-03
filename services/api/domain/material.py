from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

MaterialState = Literal["active", "archived"]
MaterialSource = Literal["seed", "user", "agent"]
ProposalState = Literal["pending", "accepted", "rejected"]


@dataclass(frozen=True, slots=True)
class MaterialDraft:
    body: str
    rationale: str
    references: tuple[dict[str, str], ...] = ()


def validate_material_content(
    title: str | None = None,
    body: str | None = None,
    rationale: str | None = None,
) -> None:
    if title is not None and (not title.strip() or len(title) > 200):
        raise ValueError("Material title is empty or too long")
    if body is not None and (not body.strip() or len(body) > 40_000):
        raise ValueError("Material body is empty or too long")
    if rationale is not None and len(rationale) > 4_000:
        raise ValueError("Proposal rationale is too long")


@dataclass(frozen=True, slots=True)
class Material:
    id: UUID
    user_id: str
    project_id: UUID | None
    title: str
    state: MaterialState
    current_version_id: UUID
    version: UUID
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MaterialVersion:
    id: UUID
    material_id: UUID
    number: int
    body: str
    source: MaterialSource
    created_at: datetime
    references: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class MaterialProposal:
    id: UUID
    material_id: UUID
    base_version_id: UUID
    proposed_body: str
    rationale: str
    state: ProposalState
    created_at: datetime
    resolved_at: datetime | None
    base_body: str
    base_number: int
    references: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class MaterialDetail:
    material: Material
    current_version: MaterialVersion
    versions: tuple[MaterialVersion, ...]
    proposals: tuple[MaterialProposal, ...]


@dataclass(frozen=True, slots=True)
class MaterialPage:
    items: tuple[Material, ...]
    next_cursor: str | None


class MaterialConflict(Exception):
    pass


class MaterialNotFound(Exception):
    pass


class MaterialInvalid(Exception):
    pass


class MaterialUnavailable(Exception):
    pass
