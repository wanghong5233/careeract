from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from services.api.application.context import ActorContext
from services.api.application.ports.boss_saved_login_viewer import (
    BossSavedLoginViewerRepository,
)
from services.api.application.ports.browser_control import (
    BrowserControlConflict,
    BrowserControlRejected,
    BrowserControlUncertain,
    BrowserSessionControl,
)
from services.api.domain.boss_saved_login_viewer import (
    BossSavedLoginViewer,
    SavedLoginViewerConflict,
    SavedLoginViewerUnavailable,
)


class BossSavedLoginViewerService:
    def __init__(
        self,
        repository: BossSavedLoginViewerRepository,
        control: BrowserSessionControl,
        *,
        lifetime: timedelta = timedelta(minutes=30),
    ) -> None:
        if not timedelta(0) < lifetime <= timedelta(hours=2):
            raise ValueError("Saved login viewer lifetime must be between 0 and 2 hours")
        self.repository = repository
        self.control = control
        self.lifetime = lifetime

    async def read(self, actor: ActorContext, connection_id: UUID) -> BossSavedLoginViewer | None:
        return await self.repository.read(actor, connection_id)

    async def open(
        self,
        actor: ActorContext,
        connection_id: UUID,
        *,
        expected_connection_version: UUID,
    ) -> BossSavedLoginViewer:
        current = await self.repository.read(actor, connection_id)
        if current is not None and current.status in ("starting", "live", "closing"):
            if current.expires_at > datetime.now(UTC):
                return current
            await self.close(
                actor,
                connection_id,
                expected_connection_version=expected_connection_version,
            )
        viewer_id = uuid4()
        session_id = uuid4()
        reserved = await self.repository.reserve(
            actor,
            connection_id,
            expected_connection_version=expected_connection_version,
            viewer_id=viewer_id,
            browser_session_id=session_id,
            expires_at=datetime.now(UTC) + self.lifetime,
        )
        context = await self.repository.context(actor, reserved.id)
        if context is None:
            raise SavedLoginViewerUnavailable("Saved login viewer context is unavailable")
        try:
            await self.control.send(context, "register")
            await self.control.lifecycle(context, "create")
        except (BrowserControlConflict, BrowserControlRejected):
            raise SavedLoginViewerConflict("Saved login viewer could not be opened") from None
        except BrowserControlUncertain:
            raise SavedLoginViewerUnavailable(
                "Saved login viewer requires reconciliation"
            ) from None
        return await self.repository.mark_live(actor, reserved.id)

    async def close(
        self,
        actor: ActorContext,
        connection_id: UUID,
        *,
        expected_connection_version: UUID,
    ) -> BossSavedLoginViewer | None:
        current = await self.repository.read(actor, connection_id)
        if current is None or current.status == "released":
            return current
        context = await self.repository.begin_close(
            actor,
            connection_id,
            expected_connection_version=expected_connection_version,
        )
        if context is None:
            return await self.repository.read(actor, connection_id)
        try:
            await self.control.send(context, "revoke")
            await self.control.lifecycle(context, "release")
        except (BrowserControlConflict, BrowserControlRejected, BrowserControlUncertain):
            raise SavedLoginViewerUnavailable(
                "Saved login viewer close requires reconciliation"
            ) from None
        return await self.repository.mark_released(actor, context.attempt_id)
