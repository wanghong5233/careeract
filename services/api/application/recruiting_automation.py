from uuid import UUID, uuid4

from services.api.application.context import ActorContext
from services.api.application.ports.boss_page import (
    conversation_message_window,
    has_bound_conversation_messages,
)
from services.api.application.ports.communication import CommunicationRepository
from services.api.application.ports.communication_send import SendDispatcher, SendRepository
from services.api.application.ports.recruiting_automation import (
    AutomationRepository,
    RecruitingStepExecutor,
)
from services.api.application.read_execution import ReadExecutionService
from services.api.domain.communication import CommunicationConflict, CommunicationUnavailable
from services.api.domain.execution import ExecutionConflict, ExecutionUnavailable
from services.api.domain.recruiting_automation import RecruitingAutomation


class RecruitingAutomationService:
    def __init__(
        self,
        repository: AutomationRepository,
        dispatcher: SendDispatcher,
        executor: RecruitingStepExecutor,
    ) -> None:
        self.repository, self.dispatcher, self.executor = repository, dispatcher, executor

    async def accept(
        self,
        actor: ActorContext,
        connection: UUID,
        version: UUID,
        key: UUID,
        conversations: tuple[str, ...],
        max_sends: int,
        duration_minutes: int,
        interval_seconds: int,
    ) -> RecruitingAutomation:
        task = await self.repository.accept(
            actor,
            connection,
            version,
            key,
            conversations,
            max_sends,
            duration_minutes,
            interval_seconds,
        )
        if task.status == "accepted":
            await self.dispatcher.dispatch(task.id)
        return task

    async def latest(self, actor: ActorContext, connection: UUID) -> RecruitingAutomation | None:
        return await self.repository.latest(actor, connection)

    async def stop(
        self, actor: ActorContext, reference: UUID, version: UUID
    ) -> RecruitingAutomation:
        await self.repository.stop(actor, reference, version)
        await self.executor.halt_automation(str(reference))
        return await self.repository.confirm_stop(actor, reference)

    async def resume_dispatch(self, actor: ActorContext, reference: UUID) -> RecruitingAutomation:
        task = await self.repository.get(actor, reference)
        if task.status == "accepted":
            await self.dispatcher.dispatch(task.id)
        return task


class RecruitingAutomationRunner:
    def __init__(
        self,
        repository: AutomationRepository,
        reads: ReadExecutionService,
        replies: CommunicationRepository,
        sends: SendRepository,
        executor: RecruitingStepExecutor,
    ) -> None:
        self.repository, self.reads, self.replies = repository, reads, replies
        self.sends, self.executor = sends, executor

    async def step(self, reference: UUID) -> int:
        step = await self.repository.claim(reference)
        if step is None:
            return 0
        task, actor = step.automation, step.actor
        try:
            if step.stage == "read":
                read = await self.reads.accept_boss(
                    actor,
                    connection_id=task.connection_id,
                    expected_version=step.connection_version,
                    request_key=uuid4(),
                    conversation_id=step.conversation_id,
                )
                # Record before I/O. A failed activity never repeats this navigation.
                if not await self.repository.finish(reference, read=read.task.id, checkpoint=True):
                    return 0
                await self.executor.read(str(read.task.id))
                current = await self.reads.read_boss(actor, task.connection_id, read.task.id)
                if current.task.status != "completed":
                    return await self.repository.finish(reference, outcome="read_requires_review")
                return await self.repository.finish(reference, stage="judge")
            if step.stage == "judge":
                if task.read_task_id is None:
                    return await self.repository.finish(reference, outcome="missing_read")
                source = await self.reads.boss_result(actor, task.connection_id, task.read_task_id)
                if (
                    source is None
                    or source.page.state != "ready"
                    or not has_bound_conversation_messages(source.page)
                ):
                    return await self.repository.finish(reference, outcome="unverified_read")
                messages = [
                    m
                    for m in conversation_message_window(source.page, step.conversation_id)
                    if m.sender in {"recruiter", "candidate"}
                ]
                if (
                    not messages
                    or messages[-1].sender != "recruiter"
                    or messages[-1].resume_attachment
                ):
                    return await self.repository.finish(reference, stage="read", advance=True)
                message = messages[-1]
                existing = await self.repository.decision_for_message(step, message.message_id)
                if existing is not None:
                    prior_send = await self.sends.get(actor, existing)
                    if prior_send is not None:
                        if prior_send.status == "completed" and not prior_send.cleanup_required:
                            return await self.repository.finish(
                                reference, stage="read", advance=True
                            )
                        return await self.repository.finish(
                            reference, outcome="send_requires_review"
                        )
                    # A saved draft is not a sent reply. Reuse its immutable source;
                    # admission still checks expiry, facts and the live message anchor.
                    return await self.repository.finish(reference, stage="send", reply=existing)
                reply = await self.replies.accept(
                    actor,
                    connection_id=task.connection_id,
                    read_task_id=task.read_task_id,
                    conversation_id=step.conversation_id,
                    message_id=message.message_id,
                    request_key=uuid4(),
                )
                if not await self.repository.finish(reference, reply=reply.id, checkpoint=True):
                    return 0
                await self.executor.generate(str(reply.id))
                return await self.repository.finish(reference, stage="send")
            if task.reply_id is None:
                return await self.repository.finish(reference, outcome="missing_reply")
            reply = await self.replies.get(actor, task.reply_id)
            if reply.decision is None:
                return await self.repository.finish(reference, outcome="judgment_requires_review")
            if reply.decision.category == "no_action":
                return await self.repository.finish(reference, stage="read", advance=True)
            if reply.decision.category not in {"routine", "acknowledgement"}:
                return await self.repository.finish(reference, outcome=reply.decision.category)
            # This specialized repository operation consumes the delegation budget atomically.
            action = await self.sends.accept(
                actor, reply.id, reply.version, uuid4(), automation_id=reference
            )
            await self.executor.send_reply(str(action.id))
            result = await self.sends.get(actor, reply.id)
            if result is None or result.status != "completed" or result.cleanup_required:
                return await self.repository.finish(reference, outcome="send_requires_review")
            return await self.repository.finish(reference, stage="read", advance=True)
        except (CommunicationConflict, ExecutionConflict):
            return await self.repository.finish(reference, outcome="scope_or_control_changed")
        except (CommunicationUnavailable, ExecutionUnavailable):
            return await self.repository.finish(reference, outcome="service_requires_review")
