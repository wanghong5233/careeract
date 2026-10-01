from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.api.application.context import ActorContext
from services.api.application.memories import MemoryService
from services.api.domain.memory import MemoryKind, MemoryState, WorkspaceMemory

router = APIRouter(prefix="/api/v1/memories", tags=["memories"])


class CreateMemoryBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: UUID | None = None
    project_id: UUID | None = None
    kind: MemoryKind
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=8000)
    source: str = Field(default="用户记录", max_length=200)


class UpdateMemoryBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=8000)
    version: UUID

    @model_validator(mode="after")
    def require_changes(self) -> "UpdateMemoryBody":
        if not (self.model_fields_set - {"version"}):
            raise ValueError("Provide memory changes")
        return self


class TransitionMemoryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: UUID


class MemoryResponse(BaseModel):
    id: UUID
    project_id: UUID | None
    kind: MemoryKind
    state: MemoryState
    title: str
    content: str
    source: str
    version: UUID
    created_at: str
    updated_at: str


class MemoryPageResponse(BaseModel):
    items: list[MemoryResponse]
    next_cursor: str | None


def get_service(request: Request) -> MemoryService:
    return cast(MemoryService, request.app.state.memory_service)


def get_actor(request: Request) -> ActorContext:
    request_id = str(uuid4())
    request.state.request_id = request_id
    return ActorContext(user_id=request.state.user_id, request_id=request_id)


def serialize(memory: WorkspaceMemory) -> MemoryResponse:
    return MemoryResponse(
        id=memory.id,
        project_id=memory.project_id,
        kind=memory.kind,
        state=memory.state,
        title=memory.title,
        content=memory.content,
        source=memory.source,
        version=memory.version,
        created_at=memory.created_at.isoformat(),
        updated_at=memory.updated_at.isoformat(),
    )


@router.get("", response_model=MemoryPageResponse)
async def list_memories(
    response: Response,
    service: Annotated[MemoryService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    kind: MemoryKind | None = None,
    include_retired: bool = False,
) -> MemoryPageResponse:
    response.headers["Cache-Control"] = "no-store"
    page = await service.list(
        actor,
        cursor=cursor,
        limit=limit,
        kind=kind,
        include_retired=include_retired,
    )
    return MemoryPageResponse(
        items=[serialize(item) for item in page.items], next_cursor=page.next_cursor
    )


@router.post("", response_model=MemoryResponse, status_code=201)
async def create_memory(
    body: CreateMemoryBody,
    response: Response,
    service: Annotated[MemoryService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> MemoryResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(
        await service.create(
            actor,
            memory_id=body.id,
            project_id=body.project_id,
            kind=body.kind,
            title=body.title,
            content=body.content,
            source=body.source,
        )
    )


@router.get("/{memory_id}", response_model=MemoryResponse)
async def read_memory(
    memory_id: UUID,
    response: Response,
    service: Annotated[MemoryService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> MemoryResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(await service.read(actor, memory_id))


@router.patch("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: UUID,
    body: UpdateMemoryBody,
    response: Response,
    service: Annotated[MemoryService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> MemoryResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(
        await service.update(
            actor,
            memory_id,
            project_id=body.project_id,
            title=body.title,
            content=body.content,
            expected_version=body.version,
        )
    )


@router.post("/{memory_id}/confirm", response_model=MemoryResponse)
async def confirm_memory(
    memory_id: UUID,
    body: TransitionMemoryBody,
    response: Response,
    service: Annotated[MemoryService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> MemoryResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(await service.confirm(actor, memory_id, expected_version=body.version))


@router.post("/{memory_id}/retire", response_model=MemoryResponse)
async def retire_memory(
    memory_id: UUID,
    body: TransitionMemoryBody,
    response: Response,
    service: Annotated[MemoryService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> MemoryResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(await service.retire(actor, memory_id, expected_version=body.version))
