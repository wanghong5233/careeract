from uuid import UUID

from services.api.application.context import ActorContext
from services.api.application.ports.work_sessions import AgentWorkSessionRepository
from services.api.domain.work_session import (
    AgentWorkSession,
    WorkSessionInvalid,
    WorkSessionNotFound,
    validate_session_id,
)


class AgentWorkSessionService:
    def __init__(self, repository: AgentWorkSessionRepository) -> None:
        self.repository = repository

    async def associate(
        self, actor: ActorContext, *, session_id: str, project_id: UUID | None
    ) -> AgentWorkSession:
        try:
            validate_session_id(session_id)
        except ValueError:
            raise WorkSessionInvalid("Invalid agent session id") from None
        session = await self.repository.associate(
            actor, session_id=session_id, project_id=project_id
        )
        if session is None:
            raise WorkSessionNotFound("Agent work session does not exist")
        return session

    async def read(self, actor: ActorContext, *, session_id: str) -> AgentWorkSession:
        try:
            validate_session_id(session_id)
        except ValueError:
            raise WorkSessionInvalid("Invalid agent session id") from None
        session = await self.repository.get(actor, session_id)
        if session is None:
            raise WorkSessionNotFound("Agent work session does not exist")
        return session
