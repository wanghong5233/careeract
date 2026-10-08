from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

BrowserAction = Literal[
    "register",
    "revoke",
    "acquire",
    "renew",
    "stop",
    "check",
    "viewer",
    "create",
    "release",
    "finish",
]


@dataclass(frozen=True)
class BrowserControlContext:
    """Trusted authorization snapshot, never constructed directly from a request body."""

    user_id: str
    session_id: UUID
    task_id: UUID
    authorization_id: UUID
    authorization_expires_at: datetime
    attempt_id: UUID
    request_id: UUID
    owner_id: str


@dataclass(frozen=True)
class BrowserLease:
    session_id: UUID
    lease_id: UUID
    owner_id: str
    expires_at: datetime
    draining: bool


@dataclass(frozen=True)
class BrowserSession:
    session_id: UUID
    status: Literal["live", "released"]
    login_verified: bool | None = None


class BrowserControlRejected(Exception):
    pass


class BrowserControlConflict(Exception):
    pass


class BrowserControlUncertain(Exception):
    pass


class BrowserSessionControl(Protocol):
    async def send(
        self, context: BrowserControlContext, action: BrowserAction, lease_id: UUID | None = None
    ) -> BrowserLease | None: ...

    async def lifecycle(
        self, context: BrowserControlContext, action: Literal["create", "release", "finish"]
    ) -> BrowserSession: ...
