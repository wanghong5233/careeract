from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.api.application.context import ActorContext
from services.api.application.ports.projects import ProjectPage
from services.api.application.projects import ProjectService
from services.api.domain.project import CareerProject, ProjectStatus

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class CreateProjectBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    id: UUID | None = None
    purpose: str = Field(default="", max_length=4000)
    status: ProjectStatus = "planned"


class UpdateProjectBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=200)
    purpose: str | None = Field(default=None, max_length=4000)
    status: ProjectStatus | None = None
    version: UUID

    @model_validator(mode="after")
    def require_changes(self) -> "UpdateProjectBody":
        changes = self.model_fields_set - {"version"}
        if not changes or any(getattr(self, field) is None for field in changes):
            raise ValueError("Provide non-null project changes")
        return self


class DeleteProjectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: UUID


class ProjectResponse(BaseModel):
    id: UUID
    title: str
    purpose: str
    status: ProjectStatus
    version: UUID
    created_at: str
    updated_at: str


class ProjectPageResponse(BaseModel):
    items: list[ProjectResponse]
    next_cursor: str | None


def get_project_service(request: Request) -> ProjectService:
    return cast(ProjectService, request.app.state.project_service)


def get_actor(request: Request) -> ActorContext:
    request_id = str(uuid4())
    request.state.request_id = request_id
    return ActorContext(user_id=request.state.user_id, request_id=request_id)


def serialize_project(project: CareerProject) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        title=project.title,
        purpose=project.purpose,
        status=project.status,
        version=project.version,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


def serialize_page(page: ProjectPage) -> ProjectPageResponse:
    return ProjectPageResponse(
        items=[serialize_project(project) for project in page.items], next_cursor=page.next_cursor
    )


@router.get("", response_model=ProjectPageResponse)
async def list_projects(
    response: Response,
    service: Annotated[ProjectService, Depends(get_project_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    archived: bool | None = None,
) -> ProjectPageResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_page(await service.list(actor, cursor=cursor, limit=limit, archived=archived))


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: CreateProjectBody,
    response: Response,
    service: Annotated[ProjectService, Depends(get_project_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ProjectResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_project(
        await service.create(
            actor, project_id=body.id, title=body.title, purpose=body.purpose, status=body.status
        )
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def read_project(
    project_id: UUID,
    response: Response,
    service: Annotated[ProjectService, Depends(get_project_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ProjectResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_project(await service.read(actor, project_id))


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    body: UpdateProjectBody,
    response: Response,
    service: Annotated[ProjectService, Depends(get_project_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ProjectResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_project(
        await service.update(
            actor,
            project_id,
            title=body.title,
            purpose=body.purpose,
            status=body.status,
            expected_version=body.version,
        )
    )


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID,
    body: DeleteProjectBody,
    service: Annotated[ProjectService, Depends(get_project_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> Response:
    await service.delete(actor, project_id, expected_version=body.version)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
