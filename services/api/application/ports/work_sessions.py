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


class AgentHistoryReader(Protocol):
    async def read(
        self, *, session_id: str, user_id: str, limit: int
    ) -> tuple[AgentHistoryMessage, ...]: ...


class AgentWorkSessionRepository(Protocol):
    async def get(self, actor: ActorContext, session_id: str) -> AgentWorkSession | None: ...

    async def associate(
        self, actor: ActorContext, *, session_id: str, project_id: UUID | None
    ) -> AgentWorkSession | None: ...
