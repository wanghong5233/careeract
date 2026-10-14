from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from services.api.domain.communication import CommunicationInvalid

AutomationStatus = Literal["accepted", "running", "waiting", "completed", "cancelled", "timed_out"]


@dataclass(frozen=True, slots=True, repr=False)
class RecruitingAutomation:
    id: UUID
    connection_id: UUID
    version: UUID
    status: AutomationStatus
    conversation_ids: tuple[str, ...]
    expires_at: datetime
    max_sends: int
    sends_reserved: int
    interval_seconds: int
    outcome: str | None
    read_task_id: UUID | None
    reply_id: UUID | None
    send_task_id: UUID | None


def validate_automation_scope(conversation_ids: tuple[str, ...], max_sends: int) -> None:
    if (
        not 1 <= len(conversation_ids) <= 20
        or len(set(conversation_ids)) != len(conversation_ids)
        or not 1 <= max_sends <= 20
    ):
        raise CommunicationInvalid("Automation requires a bounded unique conversation scope")
