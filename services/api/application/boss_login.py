from datetime import UTC, datetime, timedelta
from uuid import UUID

from services.api.application.browser_registration import BrowserRegistrationService
from services.api.application.context import ActorContext
from services.api.domain.execution import ExecutionConflict, LoginExecution


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
