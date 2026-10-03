from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from services.api.application.context import ActorContext
from services.api.application.materials import MaterialService
from services.api.domain.material import Material, MaterialDetail, MaterialProposal, MaterialVersion

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])


class CreateMaterialBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: UUID | None = None
    project_id: UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=40_000)


class SaveVersionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    base_version_id: UUID
    body: str = Field(min_length=1, max_length=40_000)


class CreateProposalBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    base_version_id: UUID
    proposed_body: str = Field(min_length=1, max_length=40_000)
    rationale: str = Field(default="", max_length=4_000)


class ResolveProposalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["accepted", "rejected"]


class VersionResponse(BaseModel):
    id: UUID
    material_id: UUID
    number: int
    body: str
    source: str
    created_at: str
    references: list[dict[str, str]]


class ProposalResponse(BaseModel):
    id: UUID
    material_id: UUID
    base_version_id: UUID
    proposed_body: str
    rationale: str
    state: str
    created_at: str
    resolved_at: str | None
    diff: list[str]
    base_body: str
    base_number: int
    references: list[dict[str, str]]
    stale: bool


class MaterialResponse(BaseModel):
    id: UUID
    project_id: UUID | None
    title: str
    state: str
    current_version_id: UUID
    version: UUID
    created_at: str
    updated_at: str
    current_version: VersionResponse | None = None
    versions: list[VersionResponse] = Field(default_factory=list)
    proposals: list[ProposalResponse] = Field(default_factory=list)


class MaterialPageResponse(BaseModel):
    items: list[MaterialResponse]
    next_cursor: str | None


def get_service(request: Request) -> MaterialService:
    return cast(MaterialService, request.app.state.material_service)


def get_actor(request: Request) -> ActorContext:
    request_id = str(uuid4())
    request.state.request_id = request_id
    return ActorContext(user_id=request.state.user_id, request_id=request_id)


def version_response(version: MaterialVersion) -> VersionResponse:
    return VersionResponse(
        id=version.id,
        material_id=version.material_id,
        number=version.number,
        body=version.body,
        source=version.source,
        created_at=version.created_at.isoformat(),
        references=list(version.references),
    )


def proposal_response(detail: MaterialDetail, proposal: MaterialProposal) -> ProposalResponse:
    return ProposalResponse(
        id=proposal.id,
        material_id=proposal.material_id,
        base_version_id=proposal.base_version_id,
        proposed_body=proposal.proposed_body,
        rationale=proposal.rationale,
        state=proposal.state,
        created_at=proposal.created_at.isoformat(),
        resolved_at=proposal.resolved_at.isoformat() if proposal.resolved_at else None,
        diff=MaterialService.diff(detail, proposal),
        base_body=proposal.base_body,
        base_number=proposal.base_number,
        references=list(proposal.references),
        stale=proposal.base_version_id != detail.current_version.id,
    )


def summary(material: Material) -> MaterialResponse:
    return MaterialResponse(
        id=material.id,
        project_id=material.project_id,
        title=material.title,
        state=material.state,
        current_version_id=material.current_version_id,
        version=material.version,
        created_at=material.created_at.isoformat(),
        updated_at=material.updated_at.isoformat(),
    )


def serialize(detail: MaterialDetail) -> MaterialResponse:
    return summary(detail.material).model_copy(
        update={
            "current_version": version_response(detail.current_version),
            "versions": [version_response(item) for item in detail.versions],
            "proposals": [proposal_response(detail, item) for item in detail.proposals],
        }
    )


@router.get("", response_model=MaterialPageResponse)
async def list_materials(
    response: Response,
    service: Annotated[MaterialService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
    project_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> MaterialPageResponse:
    response.headers["Cache-Control"] = "no-store"
    page = await service.list(actor, project_id=project_id, limit=limit, cursor=cursor)
    return MaterialPageResponse(
        items=[summary(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("", response_model=MaterialResponse, status_code=201)
async def create_material(
    body: CreateMaterialBody,
    response: Response,
    service: Annotated[MaterialService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> MaterialResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(
        await service.create(
            actor,
            material_id=body.id,
            project_id=body.project_id,
            title=body.title,
            body=body.body,
        )
    )


@router.get("/{material_id}", response_model=MaterialResponse)
async def read_material(
    material_id: UUID,
    response: Response,
    service: Annotated[MaterialService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> MaterialResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(await service.read(actor, material_id))


@router.post("/{material_id}/versions", response_model=MaterialResponse)
async def save_version(
    material_id: UUID,
    body: SaveVersionBody,
    response: Response,
    service: Annotated[MaterialService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> MaterialResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(
        await service.save_version(
            actor, material_id, base_version_id=body.base_version_id, body=body.body
        )
    )


@router.post("/{material_id}/proposals", response_model=ProposalResponse, status_code=201)
async def create_proposal(
    material_id: UUID,
    body: CreateProposalBody,
    response: Response,
    service: Annotated[MaterialService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ProposalResponse:
    response.headers["Cache-Control"] = "no-store"
    proposal = await service.propose(
        actor,
        material_id,
        base_version_id=body.base_version_id,
        proposed_body=body.proposed_body,
        rationale=body.rationale,
    )
    detail = await service.read(actor, material_id)
    return proposal_response(detail, proposal)


@router.post("/{material_id}/proposals/{proposal_id}/resolve", response_model=MaterialResponse)
async def resolve_proposal(
    material_id: UUID,
    proposal_id: UUID,
    body: ResolveProposalBody,
    response: Response,
    service: Annotated[MaterialService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> MaterialResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(await service.resolve(actor, material_id, proposal_id, state=body.state))
