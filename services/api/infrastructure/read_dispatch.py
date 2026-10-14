import asyncio
from datetime import timedelta
from uuid import UUID

from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import TemporalError, WorkflowAlreadyStartedError
from temporalio.service import RPCError

from services.api.domain.execution import ExecutionUnavailable


class TemporalReadDispatcher:
    def __init__(
        self,
        address: str,
        namespace: str,
        task_queue: str,
        *,
        workflow_name: str = "RecruitingReadWorkflow",
        id_prefix: str = "careeract-read",
        execution_minutes: int = 15,
    ) -> None:
        self.address, self.namespace, self.task_queue = address, namespace, task_queue
        self.workflow_name, self.id_prefix = workflow_name, id_prefix
        self.execution_minutes = execution_minutes

    async def dispatch(self, task_id: UUID) -> None:
        try:
            client = await asyncio.wait_for(
                Client.connect(self.address, namespace=self.namespace), timeout=8
            )
            try:
                await asyncio.wait_for(
                    client.start_workflow(
                        self.workflow_name,
                        str(task_id),
                        id=f"{self.id_prefix}-{task_id}",
                        task_queue=self.task_queue,
                        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                        execution_timeout=timedelta(minutes=self.execution_minutes),
                    ),
                    timeout=8,
                )
            except WorkflowAlreadyStartedError:
                # A completed/failed read must never navigate again. Product state is queried
                # separately; this endpoint only ensures a single durable dispatch.
                return
        except (TemporalError, RPCError, OSError, RuntimeError, TimeoutError):
            raise ExecutionUnavailable("Read was saved but dispatch is unconfirmed") from None
