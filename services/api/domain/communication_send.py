from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from services.api.domain.execution import TaskStatus


@dataclass(frozen=True, slots=True, repr=False)
class CommunicationSend:
    id: UUID
    reply_id: UUID
    connection_id: UUID
    conversation_id: str
    message_id: str
    text: str
    status: TaskStatus
    outcome: str | None
    expires_at: datetime
    evidence_message_id: str | None
    cleanup_required: bool


@dataclass(frozen=True, slots=True, repr=False)
class SendEvidence:
    state: str
    message_id: str | None = None
    cleanup_required: bool = False
