from datetime import UTC, datetime
from uuid import UUID, uuid4

from services.api.application.context import ActorContext
from services.api.application.ports.browser_control import (
    BrowserControlConflict,
    BrowserControlContext,
    BrowserControlRejected,
    BrowserControlUncertain,
    BrowserSessionControl,
)
from services.api.application.ports.execution import ExecutionRepository
from services.api.domain.execution import ExecutionAttempt, ExecutionUnavailable


class BrowserRegistrationService:
    def __init__(self, repository: ExecutionRepository, control: BrowserSessionControl) -> None:
        self.repository = repository
        self.control = control

    async def register(self, actor: ActorContext, attempt_id: UUID) -> ExecutionAttempt:
        context = await self.repository.bind_browser_session(actor, attempt_id, uuid4())
        try:
            await self.control.send(context, "register")
        except (BrowserControlRejected, BrowserControlConflict):
            return await self.repository.record_registration(
                actor, attempt_id, "registration_rejected"
            )
        except BrowserControlUncertain:
            await self.repository.record_registration(actor, attempt_id, "registration_unconfirmed")
            raise ExecutionUnavailable("Browser registration requires reconciliation") from None
        return await self.repository.record_registration(actor, attempt_id, "browser_registered")

    async def revoke(self, actor: ActorContext, attempt_id: UUID) -> ExecutionAttempt:
        attempt = await self.repository.revoke(actor, attempt_id)
        if attempt.browser_session_id is None:
            return attempt
        context = BrowserControlContext(
            user_id=actor.user_id,
            session_id=attempt.browser_session_id,
            task_id=attempt.task_id,
            authorization_id=attempt.authorization_id,
            authorization_expires_at=datetime.now(UTC),
            attempt_id=attempt.id,
            request_id=UUID(actor.request_id),
            owner_id="boss-login",
        )
        try:
            await self.control.send(context, "revoke")
        except (BrowserControlConflict, BrowserControlRejected, BrowserControlUncertain):
            raise ExecutionUnavailable("Browser revocation requires reconciliation") from None
        return attempt
