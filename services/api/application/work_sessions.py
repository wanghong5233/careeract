from datetime import UTC, datetime
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.application.ports.agent_models import AgentModelCatalog, RuntimeModel
from services.api.application.ports.work_sessions import (
    AgentHistoryReader,
    AgentWorkSessionRepository,
    ConversationDeletion,
    ConversationTitleGenerator,
    WorkSessionPage,
)
from services.api.domain.privacy import ensure_career_content
from services.api.domain.work_session import (
    AgentWorkSession,
    WorkSessionConflict,
    WorkSessionInvalid,
    WorkSessionNotFound,
    WorkSessionUnavailable,
    validate_session_id,
)


class AgentWorkSessionService:
    def __init__(self, repository: AgentWorkSessionRepository) -> None:
        self.repository = repository
        self.history: AgentHistoryReader | None = None
        self.title_generator: ConversationTitleGenerator | None = None
        self.models: AgentModelCatalog | None = None
        self.default_model: str | None = None
        self.deletion: ConversationDeletion | None = None

    async def delete(self, actor: ActorContext, *, session_id: str, expected_version: UUID) -> None:
        current = await self.read(actor, session_id=session_id)
        if current.temporary_until is not None:
            raise WorkSessionInvalid("Use temporary chat close")
        if self.deletion is None:
            raise WorkSessionUnavailable("Conversation deletion is unavailable")
        await self.deletion.delete(actor, session_id=session_id, expected_version=expected_version)

    async def runtime_models(self) -> tuple[RuntimeModel, ...]:
        if self.models is None:
            raise WorkSessionUnavailable("Model selection is unavailable")
        return await self.models.list()

    async def generate_title(
        self, actor: ActorContext, *, session_id: str, expected_version: UUID, retry: bool = False
    ) -> AgentWorkSession:
        session = await self.read(actor, session_id=session_id)
        if session.version != expected_version:
            raise WorkSessionConflict("Conversation changed; reload before naming")
        if session.title_origin != "default" or (session.title_generation_attempted and not retry):
            return session
        if self.history is None or self.title_generator is None:
            raise WorkSessionUnavailable("Conversation naming is unavailable")
        messages = await self.history.read(session_id=session_id, user_id=actor.user_id, limit=100)
        prompt = next(
            (
                message.content
                for message in messages
                if message.role == "user" and message.run_status == "COMPLETED"
            ),
            None,
        )
        if prompt is None:
            return session
        claimed = await self.repository.claim_title(
            actor, session_id=session_id, expected_version=expected_version, retry=retry
        )
        if claimed is None:
            raise WorkSessionConflict("Conversation changed; reload before naming")
        try:
            title = self.validate_title(await self.title_generator.generate(prompt[:4000]))
        except (WorkSessionUnavailable, WorkSessionInvalid):
            return await self.read(actor, session_id=session_id)
        saved = await self.repository.save_generated_title(
            actor, session_id=session_id, title=title, expected_version=claimed.version
        )
        return saved or await self.read(actor, session_id=session_id)

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
        self,
        actor: ActorContext,
        *,
        conversation_id: UUID,
        title: str,
        project_id: UUID | None,
    ) -> AgentWorkSession:
        return await self.repository.create(
            actor,
            session_id=f"conversation:{conversation_id}",
            title=self.validate_title(title),
            project_id=project_id,
            model_id=self.default_model,
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
        model_id: str | None = None,
        pinned: bool | None = None,
    ) -> AgentWorkSession:
        current = await self.read(actor, session_id=session_id)
        if current.temporary_until is not None and (
            change_project or archived is not None or title is not None or pinned is not None
        ):
            raise WorkSessionInvalid("Temporary chat scope and lifecycle use side chat endpoints")
        if (
            (change_project or archived is not None or model_id is not None)
            and self.history is not None
            and await self.history.has_active_run(session_id=session_id, user_id=actor.user_id)
        ):
            raise WorkSessionConflict("Wait for the active run to end")
        if model_id is not None:
            if self.models is None:
                raise WorkSessionUnavailable("Model selection is unavailable")
            await self.models.require(model_id)
        if (
            title is None
            and archived is None
            and not change_project
            and model_id is None
            and pinned is None
        ):
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
            model_id=model_id,
            pinned=pinned,
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
        if session_id.startswith(("conversation:", "side:")):
            raise WorkSessionInvalid("Use versioned conversation endpoints")
        session = await self.repository.associate(
            actor, session_id=session_id, project_id=project_id
        )
        if session is None:
            raise WorkSessionNotFound("Agent work session does not exist")
        return session

    async def read(
        self, actor: ActorContext, *, session_id: str, allow_expired: bool = False
    ) -> AgentWorkSession:
        try:
            validate_session_id(session_id)
        except ValueError:
            raise WorkSessionInvalid("Invalid agent session id") from None
        session = await self.repository.get(actor, session_id)
        if session is None:
            raise WorkSessionNotFound("Agent work session does not exist")
        if (
            not allow_expired
            and session.temporary_until is not None
            and session.temporary_until <= datetime.now(UTC)
        ):
            raise WorkSessionNotFound("Temporary chat has expired")
        return session
