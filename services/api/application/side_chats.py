from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.domain.work_session import AgentWorkSession


class SideChatRuntime(Protocol):
    async def create(
        self,
        actor: ActorContext,
        *,
        identifier: UUID,
        tab_id: UUID,
        source_id: str,
        message_id: str | None,
        quote: str,
    ) -> AgentWorkSession: ...

    async def close(self, actor: ActorContext, session_id: str) -> None: ...

    async def cleanup(self) -> None: ...


class SideChatService:
    def __init__(self, runtime: SideChatRuntime) -> None:
        self.runtime = runtime

    async def create(
        self,
        actor: ActorContext,
        *,
        identifier: UUID,
        tab_id: UUID,
        source_id: str,
        message_id: str | None,
        quote: str,
    ) -> AgentWorkSession:
        return await self.runtime.create(
            actor,
            identifier=identifier,
            tab_id=tab_id,
            source_id=source_id,
            message_id=message_id,
            quote=quote,
        )

    async def close(self, actor: ActorContext, session_id: str) -> None:
        await self.runtime.close(actor, session_id)
