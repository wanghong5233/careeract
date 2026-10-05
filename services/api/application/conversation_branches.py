from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.domain.work_session import AgentWorkSession


class ConversationBranchRuntime(Protocol):
    async def create(
        self,
        actor: ActorContext,
        *,
        source_id: str,
        identifier: UUID,
        message_id: str,
        mode: str,
        title: str,
        expected_version: UUID,
    ) -> AgentWorkSession: ...


class ConversationBranchService:
    def __init__(self, runtime: ConversationBranchRuntime) -> None:
        self.runtime = runtime

    async def create(
        self,
        actor: ActorContext,
        *,
        source_id: str,
        identifier: UUID,
        message_id: str,
        mode: str,
        title: str,
        expected_version: UUID,
    ) -> AgentWorkSession:
        return await self.runtime.create(
            actor,
            source_id=source_id,
            identifier=identifier,
            message_id=message_id,
            mode=mode,
            title=title,
            expected_version=expected_version,
        )
