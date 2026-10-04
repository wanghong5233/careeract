from typing import Protocol

from services.api.application.context import ActorContext


class AgentExecutionPort(Protocol):
    async def cancel(self, actor: ActorContext, session_id: str, run_id: str) -> str: ...
