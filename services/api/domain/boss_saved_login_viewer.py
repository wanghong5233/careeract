from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

SavedLoginViewerStatus = Literal["starting", "live", "closing", "released", "failed"]


@dataclass(frozen=True, slots=True)
class BossSavedLoginViewer:
    id: UUID
    user_id: str
    connection_id: UUID
    browser_session_id: UUID
    version: UUID
    status: SavedLoginViewerStatus
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class SavedLoginViewerConflict(Exception):
    pass


class SavedLoginViewerUnavailable(Exception):
    pass
