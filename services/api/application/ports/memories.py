from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.domain.memory import MemoryKind, MemoryPage, WorkspaceMemory


class MemoryRepository(Protocol):
    async def effective_rules(
        self, actor: ActorContext, *, project_id: UUID | None, limit: int
    ) -> tuple[WorkspaceMemory, ...]: ...

    async def list(
        self,
        actor: ActorContext,
        *,
        cursor: str | None,
        limit: int,
        kind: MemoryKind | None,
        include_retired: bool,
    ) -> MemoryPage: ...

    async def get(self, actor: ActorContext, memory_id: UUID) -> WorkspaceMemory | None: ...

    async def create(
        self,
        actor: ActorContext,
        *,
        memory_id: UUID,
        project_id: UUID | None,
        kind: MemoryKind,
        title: str,
        content: str,
        source: str,
    ) -> WorkspaceMemory: ...

    async def update(
        self,
        actor: ActorContext,
        memory_id: UUID,
        *,
        project_id: UUID | None,
        title: str | None,
        content: str | None,
        expected_version: UUID,
    ) -> WorkspaceMemory | None: ...

    async def transition(
        self,
        actor: ActorContext,
        memory_id: UUID,
        *,
        state: str,
        expected_version: UUID,
    ) -> WorkspaceMemory | None: ...
