import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9:_-]{1,128}$")


def validate_session_id(session_id: str) -> None:
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("Invalid agent session id")


@dataclass(frozen=True, slots=True)
class AgentWorkSession:
    session_id: str
    user_id: str
    project_id: UUID | None
    created_at: datetime
    updated_at: datetime
    title: str = "历史对话"
    archived: bool = False
    version: UUID = field(default_factory=uuid4)
    context_version: UUID = field(default_factory=uuid4)
    title_origin: str = "manual"
    title_generation_attempted: bool = False
    model_id: str | None = None

    def __post_init__(self) -> None:
        validate_session_id(self.session_id)


class WorkSessionNotFound(Exception):
    pass


class WorkSessionConflict(Exception):
    pass


class WorkSessionInvalid(Exception):
    pass


class WorkSessionUnavailable(Exception):
    pass


class WorkSessionHistoryUnavailable(Exception):
    pass
