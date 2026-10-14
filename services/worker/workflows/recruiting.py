from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError


@workflow.defn
class RecruitingReadWorkflow:
    @workflow.run
    async def run(self, task_id: str) -> None:
        try:
            await workflow.execute_activity(
                "read_recruiting_conversation",
                task_id,
                start_to_close_timeout=timedelta(seconds=120),
                schedule_to_close_timeout=timedelta(minutes=12),
                # Opening a thread marks messages read. A lost response is reconciled,
                # never replayed as another browser navigation.
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError:
            await workflow.execute_activity(
                "stop_recruiting_read",
                task_id,
                start_to_close_timeout=timedelta(seconds=45),
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            raise


@workflow.defn
class RecruitingSendWorkflow:
    @workflow.run
    async def run(self, task_id: str) -> None:
        try:
            await workflow.execute_activity(
                "send_recruiting_reply",
                task_id,
                start_to_close_timeout=timedelta(minutes=3),
                schedule_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError:
            await workflow.execute_activity(
                "reconcile_recruiting_send",
                task_id,
                start_to_close_timeout=timedelta(seconds=60),
                schedule_to_close_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            raise


@workflow.defn
class RecruitingReplyWorkflow:
    @workflow.run
    async def run(self, reply_id: str) -> None:
        # History contains an opaque reference only, not HR messages or career facts.
        # Regeneration is side-effect-free; the database claim fences late workers.
        await workflow.execute_activity(
            "generate_recruiting_reply",
            reply_id,
            start_to_close_timeout=timedelta(seconds=120),
            schedule_to_close_timeout=timedelta(minutes=15),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=95),
                maximum_attempts=3,
                maximum_interval=timedelta(seconds=95),
            ),
        )


@workflow.defn
class RecruitingAutomationWorkflow:
    @workflow.run
    async def run(self, reference: str) -> None:
        # Business scope, limits and cursor live in PostgreSQL. History gets only
        # an opaque reference and bounded timer delay, never message contents.
        for _ in range(10000):
            try:
                delay = await workflow.execute_activity(
                    "step_recruiting_automation",
                    reference,
                    start_to_close_timeout=timedelta(minutes=3),
                    schedule_to_close_timeout=timedelta(minutes=4),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                    result_type=int,
                )
            except ActivityError:
                await workflow.execute_activity(
                    "halt_recruiting_automation",
                    reference,
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                raise
            if delay == 0:
                return
            await workflow.sleep(timedelta(seconds=delay))
        await workflow.execute_activity(
            "halt_recruiting_automation",
            reference,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
