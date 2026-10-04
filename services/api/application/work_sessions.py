from uuid import UUID

from services.api.application.context import ActorContext
from services.api.application.ports.work_sessions import (
    AgentHistoryReader,
    AgentWorkSessionRepository,
    WorkSessionPage,
)
from services.api.domain.privacy import ensure_career_content
from services.api.domain.work_session import (
    AgentWorkSession,
    WorkSessionConflict,
    WorkSessionInvalid,
    WorkSessionNotFound,
    validate_session_id,
)


class AgentWorkSessionService:
    def __init__(self, repository: AgentWorkSessionRepository) -> None:
        self.repository = repository
        self.history: AgentHistoryReader | None = None

    async def list(
        self, actor: ActorContext, *, cursor: str | None, limit: int, archived: bool | None
    ) -> WorkSessionPage:
        if not 1 <= limit <= 50:
            raise WorkSessionInvalid("Invalid page size")
        return await self.repository.list(actor, cursor=cursor, limit=limit, archived=archived)

    @staticmethod
    def validate_title(title: str) -> str:
        title = title.strip()
        if not 1 <= len(title) <= 120:
            raise WorkSessionInvalid("Invalid conversation title")
        ensure_career_content(title)
        return title

    async def create(
        self, actor: ActorContext, *, conversation_id: UUID, title: str, project_id: UUID | None
    ) -> AgentWorkSession:
        return await self.repository.create(
            actor,
            session_id=f"conversation:{conversation_id}",
            title=self.validate_title(title),
            project_id=project_id,
        )

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
    ) -> AgentWorkSession:
        await self.read(actor, session_id=session_id)
        if (
            (change_project or archived is not None)
            and self.history is not None
            and await self.history.has_active_run(session_id=session_id, user_id=actor.user_id)
        ):
            raise WorkSessionConflict("Wait for the active run to end")
        if title is None and archived is None and not change_project:
            raise WorkSessionInvalid("No changes provided")
        if title is not None:
            title = self.validate_title(title)
        saved = await self.repository.update(
            actor,
            session_id=session_id,
            title=title,
            archived=archived,
            project_id=project_id,
            change_project=change_project,
            expected_version=expected_version,
        )
        if saved is None:
            raise WorkSessionConflict("Conversation changed; reload before saving")
        return saved

    async def associate(
        self, actor: ActorContext, *, session_id: str, project_id: UUID | None
    ) -> AgentWorkSession:
        try:
            validate_session_id(session_id)
        except ValueError:
            raise WorkSessionInvalid("Invalid agent session id") from None
        if session_id.startswith("conversation:"):
            raise WorkSessionInvalid("Use versioned conversation endpoints")
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
