from uuid import UUID

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.app.settings import Settings
from services.api.application.communication import generate_reply
from services.api.application.communication_send import execute_send
from services.api.application.context import ActorContext
from services.api.application.ports.browser_control import BrowserControlContext
from services.api.application.read_execution import ReadExecutionService
from services.api.application.recruiting_automation import RecruitingAutomationRunner
from services.api.domain.communication_send import SendEvidence
from services.api.domain.execution import BossReadTarget, ExecutionUnavailable
from services.api.infrastructure.boss_page import BossPageClient
from services.api.infrastructure.boss_send import BossMessageSender
from services.api.infrastructure.browser_control import BrowserCommandSigner, BrowserControlClient
from services.api.infrastructure.communication import PostgresCommunicationRepository
from services.api.infrastructure.communication_agent import AgnoReplyGenerator
from services.api.infrastructure.communication_send import PostgresSendRepository
from services.api.infrastructure.read_execution import PostgresReadExecutionRepository
from services.api.infrastructure.recruiting_automation import PostgresAutomationRepository


class RecruitingExecution:
    def __init__(self, engine: AsyncEngine, settings: Settings) -> None:
        self.engine, self.settings = engine, settings
        self.repository = PostgresCommunicationRepository(engine)
        self.generator = AgnoReplyGenerator(settings)

    async def automation_step(self, reference: str) -> int:
        delay = await RecruitingAutomationRunner(
            PostgresAutomationRepository(self.engine),
            ReadExecutionService(PostgresReadExecutionRepository(self.engine)),
            self.repository,
            PostgresSendRepository(self.engine),
            self,
        ).step(UUID(reference))
        if delay == 0:
            await self.halt_automation(reference)
        return delay

    async def halt_automation(self, reference: str) -> None:
        task = await PostgresAutomationRepository(self.engine).halt(UUID(reference))
        if task is None:
            return
        if task.read_task_id is not None:
            await self.stop_read(str(task.read_task_id))
        if task.send_task_id is not None:
            async with self.engine.connect() as db:
                needs_cleanup = await db.scalar(
                    text(
                        "SELECT t.status IN ('accepted','running') OR s.cleanup_required "
                        "FROM career.execution_tasks t JOIN career.communication_sends s "
                        "ON s.task_id=t.id WHERE t.id=:id"
                    ),
                    {"id": task.send_task_id},
                )
            if needs_cleanup:
                await self.reconcile_send(str(task.send_task_id))

    async def generate(self, reply_id: str) -> None:
        await generate_reply(self.repository, self.generator, UUID(reply_id))

    async def send_reply(self, reference: str) -> None:
        signer = self.signer()
        async with httpx.AsyncClient(
            base_url=str(self.settings.browser_base_url), timeout=50
        ) as client:
            await execute_send(
                PostgresSendRepository(self.engine),
                UUID(reference),
                BrowserControlClient(client, signer),
                BossMessageSender(client, signer),
            )

    async def reconcile_send(self, reference: str) -> None:
        task = UUID(reference)
        async with self.engine.connect() as db:
            row = (
                (
                    await db.execute(
                        text(
                            "SELECT t.user_id,t.status,x.browser_session_id,x.outcome,x.id AS "
                            "attempt,"
                            "x.request_id,a.id AS authorization,a.expires_at FROM "
                            "career.execution_tasks t "
                            "JOIN career.execution_attempts x ON x.task_id=t.id "
                            "JOIN career.execution_authorizations a ON a.task_id=t.id "
                            "WHERE t.id=:task AND t.kind='boss_reply'"
                        ),
                        {"task": task},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return
        # Cleanup only: never repeat editor input or the send control.
        if row["browser_session_id"] is not None:
            context = BrowserControlContext(
                row["user_id"],
                row["browser_session_id"],
                task,
                row["authorization"],
                row["expires_at"],
                row["attempt"],
                row["request_id"],
                "boss-reply",
            )
            async with httpx.AsyncClient(
                base_url=str(self.settings.browser_base_url), timeout=50
            ) as client:
                control = BrowserControlClient(client, self.signer())
                # Revoke also creates a tombstone if registration was in flight.
                # Checking for registration first would race a late register/create.
                await control.send(context, "revoke")
                async with self.engine.connect() as db:
                    physical = await db.scalar(
                        text("SELECT state FROM browser.steel_operations WHERE session_id=:id"),
                        {"id": context.session_id},
                    )
                if physical is not None:
                    await control.lifecycle(context, "release")
        await PostgresSendRepository(self.engine).finish(
            task,
            SendEvidence(
                "unknown" if row["outcome"] in {"send_attempted", "send_unknown"} else "failed"
            ),
        )

    async def read_actor(self, task_id: UUID) -> ActorContext | None:
        async with self.engine.connect() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT user_id FROM career.execution_tasks "
                        "WHERE id=:id AND kind='boss_read'"
                    ),
                    {"id": task_id},
                )
            ).one_or_none()
        return ActorContext(row.user_id, str(task_id)) if row else None

    def signer(self) -> BrowserCommandSigner:
        key_file = self.settings.browser_command_private_key_file
        if key_file is None or self.settings.browser_base_url is None:
            raise ExecutionUnavailable("Browser worker is not configured")
        key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ExecutionUnavailable("Browser worker signing key is invalid")
        return BrowserCommandSigner(key)

    async def read(self, reference: str) -> None:
        task_id = UUID(reference)
        actor = await self.read_actor(task_id)
        if actor is None:
            return
        service = ReadExecutionService(PostgresReadExecutionRepository(self.engine))
        current = await service.read(actor, task_id)
        if current is None or not isinstance(current.target, BossReadTarget):
            return
        if current.task.status != "accepted":
            # DB reservation fences an activity redelivery after Worker interruption.
            # Only cleanup may continue; never recreate or reopen the same thread.
            if current.task.status in {"running", "unknown"}:
                await self.stop_read(reference)
            return
        signer = self.signer()
        async with httpx.AsyncClient(
            base_url=str(self.settings.browser_base_url), timeout=50
        ) as client:
            await service.execute_boss(
                actor,
                current.target.connection_id,
                task_id,
                control=BrowserControlClient(client, signer),
                page_reader=BossPageClient(client, signer),
            )

    async def stop_read(self, reference: str) -> None:
        task_id = UUID(reference)
        actor = await self.read_actor(task_id)
        if actor is None:
            return
        service = ReadExecutionService(PostgresReadExecutionRepository(self.engine))
        current = await service.read(actor, task_id)
        if current is None or not isinstance(current.target, BossReadTarget):
            return
        if current.task.status not in {"accepted", "running", "unknown"} and not (
            current.task.status == "waiting" and current.attempt.outcome == "read_stop_requested"
        ):
            return
        signer = self.signer()
        async with httpx.AsyncClient(
            base_url=str(self.settings.browser_base_url), timeout=50
        ) as client:
            control = BrowserControlClient(client, signer)
            if current.task.status == "unknown":
                result = await service.reconcile_boss(
                    actor, current.target.connection_id, task_id, control=control
                )
            else:
                result = await service.cancel_boss(
                    actor, current.target.connection_id, task_id, control=control
                )
            if result.task.status not in {"cancelled", "failed"}:
                raise ExecutionUnavailable("Read cleanup requires release reconciliation")
