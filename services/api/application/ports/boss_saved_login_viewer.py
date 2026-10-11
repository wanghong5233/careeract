from datetime import datetime
from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.application.ports.browser_control import BrowserControlContext
from services.api.domain.boss_saved_login_viewer import BossSavedLoginViewer


class BossSavedLoginViewerRepository(Protocol):
    async def reserve(
        self,
        actor: ActorContext,
        connection_id: UUID,
        *,
        expected_connection_version: UUID,
        viewer_id: UUID,
        browser_session_id: UUID,
        expires_at: datetime,
    ) -> BossSavedLoginViewer: ...

    async def read(
        self, actor: ActorContext, connection_id: UUID
    ) -> BossSavedLoginViewer | None: ...

    async def context(
        self, actor: ActorContext, viewer_id: UUID
    ) -> BrowserControlContext | None: ...

    async def mark_live(self, actor: ActorContext, viewer_id: UUID) -> BossSavedLoginViewer: ...

    async def begin_close(
        self,
        actor: ActorContext,
        connection_id: UUID,
        *,
        expected_connection_version: UUID,
    ) -> BrowserControlContext | None: ...

    async def mark_released(self, actor: ActorContext, viewer_id: UUID) -> BossSavedLoginViewer: ...

    async def mark_failed(self, actor: ActorContext, viewer_id: UUID) -> BossSavedLoginViewer: ...
