from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.domain.communication import CommunicationReply, ReplyDecision, ReplyPage


@dataclass(frozen=True, slots=True, repr=False)
class ReplyInput:
    # Private input remains in the domain database, never in Temporal History.
    payload: dict[str, object]
    profile_facts: dict[str, str]


@dataclass(frozen=True, slots=True, repr=False)
class ReplyClaim:
    reply: CommunicationReply
    token: UUID
    source: ReplyInput


class ReplyGenerator(Protocol):
    async def generate(self, source: ReplyInput) -> ReplyDecision: ...


class ReplyDispatcher(Protocol):
    async def dispatch(self, reply_id: UUID) -> None: ...


class CommunicationRepository(Protocol):
    async def accept(
        self,
        actor: ActorContext,
        *,
        connection_id: UUID,
        read_task_id: UUID,
        conversation_id: str,
        message_id: str,
        request_key: UUID,
    ) -> CommunicationReply: ...

    async def get(self, actor: ActorContext, reply_id: UUID) -> CommunicationReply: ...

    async def list(
        self, actor: ActorContext, connection_id: UUID, cursor: UUID | None = None
    ) -> ReplyPage: ...

    async def cancel(
        self, actor: ActorContext, reply_id: UUID, expected_version: UUID
    ) -> CommunicationReply: ...

    async def claim(self, reply_id: UUID) -> ReplyClaim | None: ...

    async def finish(
        self, claim: ReplyClaim, *, decision: ReplyDecision | None, outcome: str
    ) -> None: ...
