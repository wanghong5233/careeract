from datetime import UTC, datetime, timedelta
from uuid import UUID

from services.api.application.browser_registration import BrowserRegistrationService
from services.api.application.context import ActorContext
from services.api.application.ports.browser_control import (
    BrowserControlConflict,
    BrowserControlContext,
    BrowserControlRejected,
    BrowserControlUncertain,
)
from services.api.domain.execution import ExecutionConflict, ExecutionUnavailable, LoginExecution


class BossLoginService:
    def __init__(self, browser: BrowserRegistrationService) -> None:
        self.browser = browser

    async def read(self, actor: ActorContext, connection_id: UUID) -> LoginExecution | None:
        return await self.browser.repository.read_login(actor, connection_id)

    async def start(
        self,
        actor: ActorContext,
        connection_id: UUID,
        *,
        expected_version: UUID,
        request_key: UUID,
    ) -> LoginExecution:
        _, _, attempt = await self.browser.repository.accept(
            actor,
            connection_id=connection_id,
            kind="boss_login",
            request_key=request_key,
            scope="boss.login",
            authorization_expires_at=datetime.now(UTC) + timedelta(minutes=10),
            request_id=UUID(actor.request_id),
            expected_version=expected_version,
        )
        if attempt.status == "accepted":
            registered = await self.browser.register(actor, attempt.id)
            if registered.status == "waiting" and registered.outcome == "browser_registered":
                await self.browser.create(actor, attempt.id)
        current = await self.read(actor, connection_id)
        if current is None:
            raise ExecutionConflict("Login execution is unavailable")
        return current

    async def stop(
        self, actor: ActorContext, connection_id: UUID, *, expected_version: UUID
    ) -> LoginExecution:
        current = await self.read(actor, connection_id)
        if current is None:
            raise ExecutionConflict("Login execution has not started")
        await self.browser.release(actor, current.attempt.id, expected_version=expected_version)
        result = await self.read(actor, connection_id)
        if result is None:
            raise ExecutionConflict("Login execution is unavailable")
        return result

    async def finish(
        self, actor: ActorContext, connection_id: UUID, *, expected_version: UUID
    ) -> LoginExecution:
        current = await self.read(actor, connection_id)
        if current is None:
            raise ExecutionConflict("Login execution has not started")
        if current.attempt.status == "completed" and current.attempt.outcome == "browser_released":
            return current
        if (
            current.attempt.status != "waiting"
            or current.attempt.outcome != "browser_created"
            or current.attempt.browser_session_id is None
            or current.authorization.status != "active"
            or current.authorization.expires_at <= datetime.now(UTC)
        ):
            raise ExecutionConflict("Login verification requires an active login")
        await self.browser.revoke(actor, current.attempt.id, expected_version=expected_version)
        context = BrowserControlContext(
            actor.user_id,
            current.attempt.browser_session_id,
            current.task.id,
            current.authorization.id,
            current.authorization.expires_at,
            current.attempt.id,
            UUID(actor.request_id),
            "boss-login",
        )
        try:
            result = await self.browser.control.lifecycle(context, "finish")
        except (BrowserControlConflict, BrowserControlRejected, BrowserControlUncertain):
            raise ExecutionUnavailable("Login verification requires reconciliation") from None
        await self.browser.repository.record_release(
            actor, current.attempt.id, login_verified=result.login_verified is True
        )
        updated = await self.read(actor, connection_id)
        if updated is None:
            raise ExecutionConflict("Login execution is unavailable")
        return updated

    async def forget(
        self, actor: ActorContext, connection_id: UUID, *, expected_version: UUID
    ) -> None:
        current = await self.read(actor, connection_id)
        if current is None:
            raise ExecutionConflict("Saved login has no execution evidence")
        context = await self.browser.repository.forget_context(
            actor, current.attempt.id, expected_version=expected_version
        )
        if context is None:
            return
        try:
            await self.browser.control.lifecycle(context, "forget")
        except (BrowserControlConflict, BrowserControlRejected, BrowserControlUncertain):
            raise ExecutionUnavailable("Saved login removal requires reconciliation") from None
        await self.browser.repository.record_forget(
            actor, current.attempt.id, expected_version=expected_version
        )
