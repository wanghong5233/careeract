from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

BossConnectionStatus = Literal[
    "pending",
    "waiting_for_login",
    "waiting_for_verification",
    "connected",
    "blocked",
    "revoked",
    "failed",
]

ACTIVE_BOSS_CONNECTION_STATUSES = frozenset(
    {"pending", "waiting_for_login", "waiting_for_verification", "connected", "blocked"}
)


@dataclass(frozen=True, slots=True)
class BossConnection:
    id: UUID
    user_id: str
    platform: Literal["boss"]
    request_key: UUID
    version: UUID
    browser_session_id: UUID | None
    status: BossConnectionStatus
    last_observed_url: str | None
    last_observed_state: str | None
    created_at: datetime
    updated_at: datetime


class BossConnectionConflict(Exception):
    pass


class BossConnectionNotFound(Exception):
    pass


class BossConnectionUnavailable(Exception):
    pass
