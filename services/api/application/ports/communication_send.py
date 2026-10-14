from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.application.ports.browser_control import BrowserControlContext
from services.api.domain.communication_send import CommunicationSend, SendEvidence


@dataclass(frozen=True, slots=True, repr=False)
class SendClaim:
    context: BrowserControlContext
    message_id: str
    source_text: str
    text: str


class SendRepository(Protocol):
    async def accept(
        self,
        actor: ActorContext,
        reply_id: UUID,
        version: UUID,
        request_key: UUID,
        *,
        automation_id: UUID | None = None,
    ) -> CommunicationSend: ...

    async def get(self, actor: ActorContext, reply_id: UUID) -> CommunicationSend | None: ...

    async def resume(self, actor: ActorContext, reply_id: UUID) -> CommunicationSend: ...

    async def cancel(self, actor: ActorContext, reply_id: UUID) -> CommunicationSend: ...

    async def reconcile(
        self, actor: ActorContext, reply_id: UUID, read_task_id: UUID
    ) -> CommunicationSend: ...

    async def claim(self, task_id: UUID) -> SendClaim | None: ...

    async def finish(self, task_id: UUID, evidence: SendEvidence) -> None: ...


class SendDispatcher(Protocol):
    async def dispatch(self, task_id: UUID) -> None: ...


class MessageSender(Protocol):
    async def send_message(self, claim: SendClaim) -> SendEvidence: ...
