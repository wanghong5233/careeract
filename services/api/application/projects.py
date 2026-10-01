from uuid import UUID, uuid4

from services.api.application.context import ActorContext
from services.api.application.ports.projects import ProjectPage, ProjectRepository
from services.api.domain.project import (
    CareerProject,
    ProjectConflict,
    ProjectInvalid,
    ProjectNotFound,
    ProjectStatus,
    validate_project_content,
)


class ProjectService:
    def __init__(self, repository: ProjectRepository) -> None:
        self.repository = repository

    async def list(
        self, actor: ActorContext, *, cursor: str | None, limit: int, archived: bool | None = None
    ) -> ProjectPage:
        if not 1 <= limit <= 50:
            raise ProjectInvalid("Invalid page size")
        return await self.repository.list(actor, cursor=cursor, limit=limit, archived=archived)

    async def read(self, actor: ActorContext, project_id: UUID) -> CareerProject:
        project = await self.repository.get(actor, project_id)
        if project is None:
            raise ProjectNotFound("Project does not exist")
        return project

    async def create(
        self,
        actor: ActorContext,
        *,
        title: str,
        purpose: str,
        status: ProjectStatus,
        project_id: UUID | None = None,
    ) -> CareerProject:
        title, purpose = title.strip(), purpose.strip()
        self.validate(title, purpose, status)
        return await self.repository.create(
            actor, project_id=project_id or uuid4(), title=title, purpose=purpose, status=status
        )

    async def update(
        self,
        actor: ActorContext,
        project_id: UUID,
        *,
        title: str | None,
        purpose: str | None,
        status: ProjectStatus | None,
        expected_version: UUID,
    ) -> CareerProject:
        title = title.strip() if title is not None else None
        purpose = purpose.strip() if purpose is not None else None
        if title is None and purpose is None and status is None:
            raise ProjectInvalid("No project changes provided")
        self.validate(title, purpose, status)
        project = await self.repository.update(
            actor,
            project_id,
            title=title,
            purpose=purpose,
            status=status,
            expected_version=expected_version,
        )
        if project is None:
            existing = await self.repository.get(actor, project_id)
            if existing is None:
                raise ProjectNotFound("Project does not exist")
            raise ProjectConflict("Project changed; reload before saving")
        return project

    @staticmethod
    def validate(title: str | None, purpose: str | None, status: ProjectStatus | None) -> None:
        try:
            validate_project_content(title, purpose, status)
        except ValueError:
            raise ProjectInvalid("Invalid project content") from None
