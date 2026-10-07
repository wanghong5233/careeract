from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.application.context import ActorContext
from services.api.application.ports.browser_control import BrowserControlContext
from services.api.application.ports.browser_viewer import (
    BrowserViewerTicket,
    BrowserViewerTicketRejected,
    BrowserViewerTicketUnavailable,
)
from services.api.infrastructure.browser_control import BrowserCommandSigner


class PostgresBrowserViewerTicketIssuer:
    def __init__(self, engine: AsyncEngine, signer: BrowserCommandSigner) -> None:
        self.engine = engine
        self.signer = signer

    async def issue(self, actor: ActorContext, session_id: UUID) -> BrowserViewerTicket:
        try:
            async with self.engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT task_id, authorization_id FROM browser.sessions "
                                "WHERE session_id=:session_id AND user_id=:user_id "
                                "AND revoked=false"
                            ),
                            {"session_id": session_id, "user_id": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
        except (DBAPIError, PoolTimeoutError):
            raise BrowserViewerTicketUnavailable(
                "Browser viewer authorization is unavailable"
            ) from None
        if row is None:
            raise BrowserViewerTicketRejected("Browser session is not available")

        issued_at = int(datetime.now(UTC).timestamp())
        expires_at = datetime.fromtimestamp(issued_at + 60, UTC)
        try:
            request_id = UUID(actor.request_id)
        except ValueError:
            raise BrowserViewerTicketRejected("Invalid browser request context") from None
        context = BrowserControlContext(
            user_id=actor.user_id,
            session_id=session_id,
            task_id=row["task_id"],
            authorization_id=row["authorization_id"],
            authorization_expires_at=expires_at,
            attempt_id=uuid4(),
            request_id=request_id,
            owner_id="viewer",
        )
        try:
            token = self.signer.sign(context, "viewer")
        except (ValueError, TypeError):
            raise BrowserViewerTicketUnavailable(
                "Browser viewer authorization is unavailable"
            ) from None
        return BrowserViewerTicket(session_id, token, expires_at)
