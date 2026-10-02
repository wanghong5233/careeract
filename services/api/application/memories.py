from uuid import UUID, uuid4

from services.api.application.context import ActorContext
from services.api.application.ports.memories import MemoryRepository
from services.api.domain.memory import (
    MemoryConflict,
    MemoryInvalid,
    MemoryKind,
    MemoryNotFound,
    MemoryPage,
    WorkspaceMemory,
    validate_memory_content,
)
from services.api.domain.privacy import ensure_career_content


class MemoryService:
    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    async def effective_rules(
        self, actor: ActorContext, *, project_id: UUID | None
    ) -> tuple[WorkspaceMemory, ...]:
        rules = await self.repository.effective_rules(actor, project_id=project_id, limit=101)
        if len(rules) > 100:
            raise MemoryInvalid("Effective rules exceed the run context limit")
        return rules

    async def list(
        self,
        actor: ActorContext,
        *,
        cursor: str | None,
        limit: int,
        kind: MemoryKind | None,
        include_retired: bool,
    ) -> MemoryPage:
        if not 1 <= limit <= 50:
            raise MemoryInvalid("Invalid page size")
        if kind is not None:
            self.validate(kind=kind)
        return await self.repository.list(
            actor,
            cursor=cursor,
            limit=limit,
            kind=kind,
            include_retired=include_retired,
        )

    async def read(self, actor: ActorContext, memory_id: UUID) -> WorkspaceMemory:
        memory = await self.repository.get(actor, memory_id)
        if memory is None:
            raise MemoryNotFound("Memory does not exist")
        return memory

    async def create(
        self,
        actor: ActorContext,
        *,
        memory_id: UUID | None,
        project_id: UUID | None,
        kind: MemoryKind,
        title: str,
        content: str,
        source: str,
    ) -> WorkspaceMemory:
        title, content, source = title.strip(), content.strip(), source.strip()
        self.validate(kind=kind, title=title, content=content, source=source)
        return await self.repository.create(
            actor,
            memory_id=memory_id or uuid4(),
            project_id=project_id,
            kind=kind,
            title=title,
            content=content,
            source=source,
        )

    async def update(
        self,
        actor: ActorContext,
        memory_id: UUID,
        *,
        project_id: UUID | None,
        title: str | None,
        content: str | None,
        expected_version: UUID,
    ) -> WorkspaceMemory:
        title = title.strip() if title is not None else None
        content = content.strip() if content is not None else None
        if title is None and content is None and project_id is None:
            raise MemoryInvalid("No memory changes provided")
        self.validate(title=title, content=content)
        memory = await self.repository.update(
            actor,
            memory_id,
            project_id=project_id,
            title=title,
            content=content,
            expected_version=expected_version,
        )
        if memory is None:
            existing = await self.repository.get(actor, memory_id)
            if existing is None:
                raise MemoryNotFound("Memory does not exist")
            raise MemoryConflict("Memory changed; reload before saving")
        return memory

    async def confirm(
        self, actor: ActorContext, memory_id: UUID, *, expected_version: UUID
    ) -> WorkspaceMemory:
        current = await self.read(actor, memory_id)
        if current.kind != "rule":
            raise MemoryInvalid("Only rules require explicit confirmation")
        if current.state == "retired":
            raise MemoryInvalid("Retired memory cannot be confirmed")
        self.validate(title=current.title, content=current.content, source=current.source)
        memory = await self.repository.transition(
            actor, memory_id, state="confirmed", expected_version=expected_version
        )
        if memory is None:
            raise MemoryConflict("Memory changed; reload before confirming")
        return memory

    async def retire(
        self, actor: ActorContext, memory_id: UUID, *, expected_version: UUID
    ) -> WorkspaceMemory:
        await self.read(actor, memory_id)
        memory = await self.repository.transition(
            actor, memory_id, state="retired", expected_version=expected_version
        )
        if memory is None:
            raise MemoryConflict("Memory changed; reload before retiring")
        return memory

    @staticmethod
    def validate(
        *,
        kind: MemoryKind | None = None,
        title: str | None = None,
        content: str | None = None,
        source: str | None = None,
    ) -> None:
        try:
            validate_memory_content(kind, None, title, content, source)
        except ValueError:
            raise MemoryInvalid("Invalid memory content") from None
        ensure_career_content((title, content, source))
