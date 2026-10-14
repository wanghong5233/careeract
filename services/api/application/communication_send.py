from dataclasses import replace
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.application.ports.browser_control import (
    BrowserControlConflict,
    BrowserControlRejected,
    BrowserControlUncertain,
    BrowserSessionControl,
)
from services.api.application.ports.communication_send import (
    MessageSender,
    SendDispatcher,
    SendRepository,
)
from services.api.domain.communication_send import CommunicationSend, SendEvidence
from services.api.domain.execution import ExecutionUnavailable


class CommunicationSendService:
    def __init__(self, repository: SendRepository, dispatcher: SendDispatcher) -> None:
        self.repository, self.dispatcher = repository, dispatcher

    async def authorize(
        self, actor: ActorContext, reply_id: UUID, version: UUID, request_key: UUID
    ) -> CommunicationSend:
        action = await self.repository.accept(actor, reply_id, version, request_key)
        if action.status == "accepted":
            await self.dispatcher.dispatch(action.id)
        return action

    async def get(self, actor: ActorContext, reply_id: UUID) -> CommunicationSend | None:
        return await self.repository.get(actor, reply_id)

    async def resume(self, actor: ActorContext, reply_id: UUID) -> CommunicationSend:
        action = await self.repository.resume(actor, reply_id)
        if action.status == "accepted":
            await self.dispatcher.dispatch(action.id)
        return action

    async def cancel(self, actor: ActorContext, reply_id: UUID) -> CommunicationSend:
        return await self.repository.cancel(actor, reply_id)

    async def reconcile(
        self, actor: ActorContext, reply_id: UUID, read_task_id: UUID
    ) -> CommunicationSend:
        return await self.repository.reconcile(actor, reply_id, read_task_id)


async def execute_send(
    repository: SendRepository,
    task_id: UUID,
    control: BrowserSessionControl,
    sender: MessageSender,
) -> None:
    claim = await repository.claim(task_id)
    if claim is None:
        return
    context = claim.context
    lifecycle_context = replace(context, conversation_id=None)
    evidence = SendEvidence("unknown")
    registered = False
    create_attempted = False
    send_attempted = False
    try:
        registered = True
        await control.send(lifecycle_context, "register")
        create_attempted = True
        await control.lifecycle(lifecycle_context, "create")
        send_attempted = True
        evidence = await sender.send_message(claim)
    except (BrowserControlRejected, BrowserControlConflict):
        # A rejected command cannot have entered the send adapter.
        evidence = SendEvidence("failed")
    except BrowserControlUncertain:
        evidence = SendEvidence("unknown" if send_attempted else "failed")
    finally:
        if registered:
            try:
                await control.send(lifecycle_context, "revoke")
                if create_attempted:
                    await control.lifecycle(lifecycle_context, "release")
            except (BrowserControlRejected, BrowserControlConflict, BrowserControlUncertain):
                # Retain successful delivery evidence even if physical cleanup failed.
                evidence = replace(evidence, cleanup_required=True)
        await repository.finish(task_id, evidence)
        if evidence.cleanup_required:
            raise ExecutionUnavailable(
                "Send evidence saved; browser cleanup requires reconciliation"
            )
