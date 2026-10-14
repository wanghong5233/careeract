import asyncio
from datetime import timedelta
from uuid import UUID

from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import TemporalError, WorkflowAlreadyStartedError
from temporalio.service import RPCError

from services.api.domain.communication import CommunicationUnavailable


class TemporalReplyDispatcher:
    def __init__(self, address: str, namespace: str, task_queue: str) -> None:
        self.address, self.namespace, self.task_queue = address, namespace, task_queue

    async def dispatch(self, reply_id: UUID) -> None:
        try:
            client = await asyncio.wait_for(
                Client.connect(self.address, namespace=self.namespace), timeout=8
            )
            workflow_id = f"careeract-reply-{reply_id}"
            try:
                await asyncio.wait_for(
                    client.start_workflow(
                        "RecruitingReplyWorkflow",
                        str(reply_id),
                        id=workflow_id,
                        task_queue=self.task_queue,
                        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                        execution_timeout=timedelta(minutes=15),
                    ),
                    timeout=8,
                )
            except WorkflowAlreadyStartedError:
                description = await asyncio.wait_for(
                    client.get_workflow_handle(workflow_id).describe(), timeout=8
                )
                if description.status != WorkflowExecutionStatus.RUNNING:
                    raise CommunicationUnavailable(
                        "Reply workflow requires reconciliation"
                    ) from None
        except (TemporalError, RPCError, OSError, RuntimeError, TimeoutError):
            raise CommunicationUnavailable(
                "Reply was saved but workflow dispatch is unconfirmed"
            ) from None
