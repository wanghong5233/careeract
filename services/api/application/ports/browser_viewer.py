from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from services.api.application.context import ActorContext


@dataclass(frozen=True, slots=True)
class BrowserViewerTicket:
    session_id: UUID
    token: str
    expires_at: datetime
    mode: Literal["control", "watch"] = "control"


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
    async def issue(
        self,
        actor: ActorContext,
        session_id: UUID,
        *,
        mode: Literal["control", "watch"] = "control",
    ) -> BrowserViewerTicket: ...

    async def document(
        self,
        actor: ActorContext,
        session_id: UUID,
        page_id: str | None,
        *,
        mode: Literal["control", "watch"] = "control",
    ) -> BrowserViewerDocument: ...

    async def renew(
        self,
        actor: ActorContext,
        session_id: UUID,
        *,
        mode: Literal["control", "watch"] = "control",
    ) -> None: ...
