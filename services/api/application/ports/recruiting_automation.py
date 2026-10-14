from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.domain.recruiting_automation import RecruitingAutomation


@dataclass(frozen=True, slots=True)
class AutomationStep:
    actor: ActorContext
    automation: RecruitingAutomation
    connection_version: UUID
    conversation_id: str
    stage: str


class AutomationRepository(Protocol):
    async def accept(
        self,
        actor: ActorContext,
        connection: UUID,
        version: UUID,
        key: UUID,
        conversations: tuple[str, ...],
        max_sends: int,
        duration_minutes: int,
        interval_seconds: int,
    ) -> RecruitingAutomation: ...

    async def latest(
        self, actor: ActorContext, connection: UUID
    ) -> RecruitingAutomation | None: ...

    async def get(self, actor: ActorContext, reference: UUID) -> RecruitingAutomation: ...

    async def stop(
        self, actor: ActorContext, reference: UUID, version: UUID
    ) -> RecruitingAutomation: ...

    async def confirm_stop(self, actor: ActorContext, reference: UUID) -> RecruitingAutomation: ...

    async def claim(self, reference: UUID) -> AutomationStep | None: ...

    async def decision_for_message(self, step: AutomationStep, message_id: str) -> UUID | None: ...

    async def finish(
        self,
        reference: UUID,
        *,
        stage: str | None = None,
        outcome: str | None = None,
        advance: bool = False,
        read: UUID | None = None,
        reply: UUID | None = None,
        checkpoint: bool = False,
    ) -> int: ...


class RecruitingStepExecutor(Protocol):
    async def halt_automation(self, reference: str) -> None: ...

    async def generate(self, reference: str) -> None: ...

    async def read(self, reference: str) -> None: ...

    async def send_reply(self, reference: str) -> None: ...
