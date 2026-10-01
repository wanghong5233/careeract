from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.domain.work_session import AgentWorkSession


class AgentWorkSessionRepository(Protocol):
    async def get(self, actor: ActorContext, session_id: str) -> AgentWorkSession | None: ...

    async def associate(
        self, actor: ActorContext, *, session_id: str, project_id: UUID | None
    ) -> AgentWorkSession | None: ...
