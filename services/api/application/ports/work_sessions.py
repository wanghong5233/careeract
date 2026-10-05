from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.domain.work_session import AgentWorkSession


@dataclass(frozen=True, slots=True)
class AgentHistoryMessage:
    id: str
    role: str
    content: str
    created_at: int
    run_id: str | None = None
    run_status: str = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class WorkSessionPage:
    items: tuple[AgentWorkSession, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class AgentContextBasis:
    run_id: str | None
    references: tuple[dict[str, str], ...] = ()
    proposals: tuple[dict[str, str], ...] = ()


class AgentHistoryReader(Protocol):
    async def has_active_run(self, *, session_id: str, user_id: str) -> bool: ...

    async def basis(self, *, session_id: str, user_id: str) -> AgentContextBasis: ...

    async def read(
        self, *, session_id: str, user_id: str, limit: int
    ) -> tuple[AgentHistoryMessage, ...]: ...


class AgentWorkSessionRepository(Protocol):
    async def claim_title(
        self, actor: ActorContext, *, session_id: str, expected_version: UUID
    ) -> AgentWorkSession | None: ...

    async def save_generated_title(
        self, actor: ActorContext, *, session_id: str, title: str, expected_version: UUID
    ) -> AgentWorkSession | None: ...

    async def list(
        self, actor: ActorContext, *, cursor: str | None, limit: int, archived: bool | None
    ) -> WorkSessionPage: ...

    async def create(
        self, actor: ActorContext, *, session_id: str, title: str, project_id: UUID | None
    ) -> AgentWorkSession: ...

    async def update(
        self,
        actor: ActorContext,
        *,
        session_id: str,
        title: str | None,
        archived: bool | None,
        project_id: UUID | None,
        change_project: bool,
        expected_version: UUID,
    ) -> AgentWorkSession | None: ...

    async def get(self, actor: ActorContext, session_id: str) -> AgentWorkSession | None: ...

    async def associate(
        self, actor: ActorContext, *, session_id: str, project_id: UUID | None
    ) -> AgentWorkSession | None: ...


class ConversationTitleGenerator(Protocol):
    async def generate(self, prompt: str) -> str: ...
