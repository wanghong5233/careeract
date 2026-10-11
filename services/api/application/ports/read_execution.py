from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.application.ports.boss_page import BossPageObservation
from services.api.application.ports.browser_control import BrowserControlContext
from services.api.domain.execution import ReadExecution, ReadTarget


@dataclass(frozen=True, slots=True, repr=False)
class ReadPageResult:
    observed_at: datetime
    page: BossPageObservation


class ReadExecutionRepository(Protocol):
    async def accept(
        self,
        actor: ActorContext,
        *,
        target: ReadTarget,
        request_key: UUID,
        authorization_lifetime: timedelta,
    ) -> ReadExecution: ...

    async def read(self, actor: ActorContext, task_id: UUID) -> ReadExecution | None: ...

    async def cancel(self, actor: ActorContext, task_id: UUID) -> ReadExecution: ...

    async def reconcile_released(
        self, actor: ActorContext, task_id: UUID, *, allow_absent: bool = False
    ) -> ReadExecution: ...

    async def reserve_browser(
        self, actor: ActorContext, task_id: UUID, session_id: UUID
    ) -> BrowserControlContext: ...

    async def finish_browser(
        self,
        actor: ActorContext,
        task_id: UUID,
        *,
        outcome: str,
        observation: BossPageObservation | None = None,
    ) -> ReadExecution: ...

    async def read_latest_boss(
        self, actor: ActorContext, connection_id: UUID
    ) -> ReadExecution | None: ...

    async def read_page_result(
        self, actor: ActorContext, task_id: UUID
    ) -> ReadPageResult | None: ...
