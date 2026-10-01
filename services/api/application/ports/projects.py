from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.domain.project import CareerProject, ProjectStatus


@dataclass(frozen=True, slots=True)
class ProjectPage:
    items: tuple[CareerProject, ...]
    next_cursor: str | None


class ProjectRepository(Protocol):
    async def list(
        self, actor: ActorContext, *, cursor: str | None, limit: int, archived: bool | None
    ) -> ProjectPage: ...

    async def get(self, actor: ActorContext, project_id: UUID) -> CareerProject | None: ...

    async def create(
        self,
        actor: ActorContext,
        *,
        project_id: UUID,
        title: str,
        purpose: str,
        status: ProjectStatus,
    ) -> CareerProject: ...

    async def update(
        self,
        actor: ActorContext,
        project_id: UUID,
        *,
        title: str | None,
        purpose: str | None,
        status: ProjectStatus | None,
        expected_version: UUID,
    ) -> CareerProject | None: ...
