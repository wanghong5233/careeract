from uuid import UUID

from services.api.application.context import ActorContext
from services.api.application.ports.communication import (
    CommunicationRepository,
    ReplyDispatcher,
    ReplyGenerator,
)
from services.api.domain.communication import (
    CommunicationInvalid,
    CommunicationReply,
    CommunicationUnavailable,
    ReplyPage,
    validate_reply_decision,
)
from services.api.domain.privacy import RestrictedContent, ensure_career_content


class CommunicationService:
    def __init__(self, repository: CommunicationRepository, dispatcher: ReplyDispatcher) -> None:
        self.repository, self.dispatcher = repository, dispatcher

    async def accept_reply(
        self,
        actor: ActorContext,
        *,
        connection_id: UUID,
        read_task_id: UUID,
        conversation_id: str,
        message_id: str,
        request_key: UUID,
    ) -> CommunicationReply:
        reply = await self.repository.accept(
            actor,
            connection_id=connection_id,
            read_task_id=read_task_id,
            conversation_id=conversation_id,
            message_id=message_id,
            request_key=request_key,
        )
        # Same-key replay dispatches the same workflow, never creates a new generation.
        if reply.status == "accepted":
            await self.dispatcher.dispatch(reply.id)
        return reply

    async def get(self, actor: ActorContext, reply_id: UUID) -> CommunicationReply:
        return await self.repository.get(actor, reply_id)

    async def list(
        self, actor: ActorContext, connection_id: UUID, cursor: UUID | None = None
    ) -> ReplyPage:
        return await self.repository.list(actor, connection_id, cursor)

    async def resume(self, actor: ActorContext, reply_id: UUID) -> CommunicationReply:
        reply = await self.repository.get(actor, reply_id)
        if reply.status == "accepted":
            await self.dispatcher.dispatch(reply.id)
        return reply

    async def cancel(
        self, actor: ActorContext, reply_id: UUID, expected_version: UUID
    ) -> CommunicationReply:
        return await self.repository.cancel(actor, reply_id, expected_version)


async def generate_reply(
    repository: CommunicationRepository, generator: ReplyGenerator, reply_id: UUID
) -> None:
    claim = await repository.claim(reply_id)
    if claim is None:
        return
    try:
        ensure_career_content(claim.source.payload)
        decision = validate_reply_decision(
            await generator.generate(claim.source), claim.source.profile_facts
        )
        ensure_career_content({"text": decision.text, "reason": decision.reason})
    except CommunicationInvalid:
        await repository.finish(claim, decision=None, outcome="invalid_model_result")
        return
    except RestrictedContent:
        await repository.finish(claim, decision=None, outcome="restricted_model_result")
        return
    except CommunicationUnavailable:
        await repository.finish(claim, decision=None, outcome="model_unavailable")
        return
    await repository.finish(claim, decision=decision, outcome="decision_completed")
