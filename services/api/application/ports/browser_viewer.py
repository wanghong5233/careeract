from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from services.api.application.context import ActorContext


@dataclass(frozen=True, slots=True)
class BrowserViewerTicket:
    session_id: UUID
    token: str
    expires_at: datetime


class BrowserViewerTicketRejected(Exception):
    pass


class BrowserViewerTicketUnavailable(Exception):
    pass


class BrowserViewerTicketIssuer(Protocol):
    async def issue(self, actor: ActorContext, session_id: UUID) -> BrowserViewerTicket: ...
