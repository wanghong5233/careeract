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


@dataclass(frozen=True, slots=True)
class BrowserViewerDocument:
    content: bytes
    content_type: str
    set_cookie: str | None


class BrowserViewerTicketRejected(Exception):
    pass


class BrowserViewerTicketUnavailable(Exception):
    pass


class BrowserViewerTicketIssuer(Protocol):
    async def issue(self, actor: ActorContext, session_id: UUID) -> BrowserViewerTicket: ...

    async def document(
        self, actor: ActorContext, session_id: UUID, page_id: str | None
    ) -> BrowserViewerDocument: ...

    async def renew(self, actor: ActorContext, session_id: UUID) -> None: ...
