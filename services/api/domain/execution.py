from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

TaskStatus = Literal[
    "accepted", "running", "waiting", "failed", "timed_out", "cancelled", "completed"
]
AuthorizationStatus = Literal["active", "revoked", "expired"]
AttemptStatus = Literal[
    "accepted", "running", "waiting", "unknown", "failed", "cancelled", "completed"
]


@dataclass(frozen=True, slots=True)
class ExecutionTask:
    id: UUID
    user_id: str
    kind: str
    request_key: UUID
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    connection_id: UUID


@dataclass(frozen=True, slots=True)
class ExecutionAuthorization:
    id: UUID
    task_id: UUID
    user_id: str
    scope: str
    status: AuthorizationStatus
    expires_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExecutionAttempt:
    id: UUID
    task_id: UUID
    authorization_id: UUID
    user_id: str
    request_id: UUID
    status: AttemptStatus
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    browser_session_id: UUID | None = None
    outcome: str | None = None


@dataclass(frozen=True, slots=True)
class LoginExecution:
    task: ExecutionTask
    authorization: ExecutionAuthorization
    attempt: ExecutionAttempt


class ExecutionConflict(Exception):
    pass


class ExecutionUnavailable(Exception):
    pass
