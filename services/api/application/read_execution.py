from contextlib import suppress
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

from services.api.application.context import ActorContext
from services.api.application.ports.boss_page import BossPageObservation, BossPageReader
from services.api.application.ports.browser_control import (
    BrowserControlConflict,
    BrowserControlContext,
    BrowserControlRejected,
    BrowserControlUncertain,
    BrowserSessionControl,
)
from services.api.application.ports.read_execution import ReadExecutionRepository, ReadPageResult
from services.api.domain.execution import (
    BossReadTarget,
    ExecutionConflict,
    ExecutionNotFound,
    ExecutionUnavailable,
    MaterialReadTarget,
    ReadExecution,
)


class ReadExecutionService:
    def __init__(self, repository: ReadExecutionRepository) -> None:
        self.repository = repository

    async def accept_boss(
        self,
        actor: ActorContext,
        *,
        connection_id: UUID,
        expected_version: UUID,
        request_key: UUID,
    ) -> ReadExecution:
        return await self.repository.accept(
            actor,
            target=BossReadTarget(connection_id, expected_version),
            request_key=request_key,
            authorization_lifetime=timedelta(minutes=15),
        )

    async def accept_material(
        self,
        actor: ActorContext,
        *,
        material_id: UUID,
        version_id: UUID,
        expected_version: UUID,
        request_key: UUID,
    ) -> ReadExecution:
        return await self.repository.accept(
            actor,
            target=MaterialReadTarget(material_id, version_id, expected_version),
            request_key=request_key,
            authorization_lifetime=timedelta(minutes=15),
        )

    async def read(self, actor: ActorContext, task_id: UUID) -> ReadExecution | None:
        return await self.repository.read(actor, task_id)

    async def latest_boss(self, actor: ActorContext, connection_id: UUID) -> ReadExecution | None:
        return await self.repository.read_latest_boss(actor, connection_id)

    async def boss_result(
        self, actor: ActorContext, connection_id: UUID, task_id: UUID
    ) -> ReadPageResult | None:
        await self.read_boss(actor, connection_id, task_id)
        return await self.repository.read_page_result(actor, task_id)

    async def cancel(self, actor: ActorContext, task_id: UUID) -> ReadExecution:
        return await self.repository.cancel(actor, task_id)

    async def read_boss(
        self, actor: ActorContext, connection_id: UUID, task_id: UUID
    ) -> ReadExecution:
        execution = await self.read(actor, task_id)
        if (
            execution is None
            or not isinstance(execution.target, BossReadTarget)
            or execution.target.connection_id != connection_id
        ):
            raise ExecutionNotFound("Read execution is unavailable")
        return execution

    async def cancel_boss(
        self,
        actor: ActorContext,
        connection_id: UUID,
        task_id: UUID,
        *,
        control: BrowserSessionControl | None = None,
    ) -> ReadExecution:
        await self.read_boss(actor, connection_id, task_id)
        execution = await self.cancel(actor, task_id)
        if execution.task.status != "waiting" or control is None:
            return execution
        session_id = execution.attempt.browser_session_id
        if session_id is None:
            raise ExecutionUnavailable("Read browser identity is unavailable")
        context = BrowserControlContext(
            actor.user_id,
            session_id,
            task_id,
            execution.authorization.id,
            execution.authorization.expires_at,
            execution.attempt.id,
            execution.attempt.request_id,
            "boss-read",
        )
        try:
            await control.send(context, "revoke")
            with suppress(BrowserControlConflict, BrowserControlRejected, BrowserControlUncertain):
                await control.lifecycle(context, "release")
            return await self.repository.reconcile_released(actor, task_id)
        except (
            BrowserControlConflict,
            BrowserControlRejected,
            BrowserControlUncertain,
            ExecutionConflict,
        ):
            return await self.read_boss(actor, connection_id, task_id)

    async def reconcile_boss(
        self,
        actor: ActorContext,
        connection_id: UUID,
        task_id: UUID,
        *,
        control: BrowserSessionControl | None = None,
    ) -> ReadExecution:
        execution = await self.read_boss(actor, connection_id, task_id)
        if (
            execution.task.status == "waiting"
            and execution.attempt.outcome == "read_stop_requested"
        ):
            return await self.cancel_boss(actor, connection_id, task_id, control=control)
        allow_absent = False
        if execution.task.status == "unknown" and control is not None:
            session_id = execution.attempt.browser_session_id
            if session_id is None:
                raise ExecutionUnavailable("Read browser identity is unavailable")
            context = BrowserControlContext(
                actor.user_id,
                session_id,
                task_id,
                execution.authorization.id,
                execution.authorization.expires_at,
                execution.attempt.id,
                execution.attempt.request_id,
                "boss-read",
            )
            try:
                await control.send(context, "revoke")
            except BrowserControlRejected:
                # Registration may fail before Browser Service persists a session row.
                # Repository reconciliation still requires either a released row or no row.
                allow_absent = True
            except (BrowserControlConflict, BrowserControlUncertain):
                raise ExecutionUnavailable(
                    "Read browser revocation requires reconciliation"
                ) from None
        return await self.repository.reconcile_released(actor, task_id, allow_absent=allow_absent)

    async def execute_boss(
        self,
        actor: ActorContext,
        connection_id: UUID,
        task_id: UUID,
        *,
        control: BrowserSessionControl,
        page_reader: BossPageReader,
    ) -> ReadExecution:
        await self.read_boss(actor, connection_id, task_id)
        await self.run_boss_read(actor, task_id, control=control, page_reader=page_reader)
        return await self.read_boss(actor, connection_id, task_id)

    async def run_boss_read(
        self,
        actor: ActorContext,
        task_id: UUID,
        *,
        control: BrowserSessionControl,
        page_reader: BossPageReader,
    ) -> BossPageObservation:
        context = await self.repository.reserve_browser(actor, task_id, uuid4())
        registered = False
        create_attempted = False
        created = False
        outcome = "read_unknown"
        observation: BossPageObservation | None = None
        try:
            try:
                await control.send(context, "register")
            except BrowserControlUncertain:
                registered = True
                raise
            registered = True
            create_attempted = True
            await control.lifecycle(context, "create")
            created = True
            observation = await page_reader.read_boss_page(
                replace(context, owner_id="boss-page-reader")
            )
            if observation.state == "ready" and observation.kind != "unknown":
                outcome = "read_completed"
            elif observation.state in {"needs_login", "risk"}:
                outcome = "read_failed"
        except (BrowserControlRejected, BrowserControlConflict):
            outcome = "read_failed"
        except BrowserControlUncertain:
            outcome = "read_unknown"
        finally:
            if registered:
                try:
                    await control.send(context, "revoke")
                    if create_attempted:
                        await control.lifecycle(context, "release")
                    if created and outcome == "read_unknown":
                        outcome = "read_failed"
                except (BrowserControlConflict, BrowserControlRejected, BrowserControlUncertain):
                    outcome = "read_unknown"
            finished = await self.repository.finish_browser(
                actor, task_id, outcome=outcome, observation=observation
            )
            if (
                finished.task.status == "waiting"
                and finished.attempt.outcome == "read_stop_requested"
            ):
                with suppress(ExecutionConflict):
                    await self.repository.reconcile_released(actor, task_id)
        if observation is None or outcome != "read_completed":
            if outcome == "read_failed":
                raise ExecutionUnavailable("BOSS read execution was rejected")
            raise ExecutionUnavailable("BOSS read execution requires reconciliation")
        return observation
