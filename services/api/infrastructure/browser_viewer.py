from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.application.context import ActorContext
from services.api.application.ports.browser_control import (
    BrowserControlContext,
    BrowserControlRejected,
)
from services.api.application.ports.browser_viewer import (
    BrowserViewerDocument,
    BrowserViewerTicket,
    BrowserViewerTicketRejected,
    BrowserViewerTicketUnavailable,
)
from services.api.infrastructure.browser_control import BrowserCommandSigner


class PostgresBrowserViewerTicketIssuer:
    def __init__(
        self,
        engine: AsyncEngine,
        signer: BrowserCommandSigner,
        browser_client: httpx.AsyncClient | None = None,
        viewer_origin: str | None = None,
    ) -> None:
        self.engine = engine
        self.signer = signer
        self.browser_client = browser_client
        self.viewer_origin = str(viewer_origin).rstrip("/") if viewer_origin else None

    async def document(
        self, actor: ActorContext, session_id: UUID, page_id: str | None
    ) -> BrowserViewerDocument:
        if self.browser_client is None or self.viewer_origin is None:
            raise BrowserViewerTicketUnavailable("Browser viewer is not configured")
        ticket = await self.issue(actor, session_id)
        try:
            response = await self.browser_client.get(
                f"/internal/v1/sessions/{session_id}/viewer",
                params={"pageId": page_id} if page_id is not None else None,
                headers={
                    "Authorization": "Bearer " + ticket.token,
                    "Origin": self.viewer_origin,
                },
                follow_redirects=False,
                timeout=20,
            )
        except httpx.TransportError:
            raise BrowserViewerTicketUnavailable("Browser viewer is unavailable") from None
        if response.status_code in (401, 403, 404, 409):
            raise BrowserViewerTicketRejected("Browser session is not available")
        if (
            response.status_code != 200
            or response.headers.get("content-type", "").split(";", 1)[0] != "text/html"
        ):
            raise BrowserViewerTicketUnavailable("Browser viewer response is invalid")
        return BrowserViewerDocument(
            response.content,
            response.headers.get("content-type", "text/html"),
            response.headers.get("set-cookie"),
        )

    async def issue(self, actor: ActorContext, session_id: UUID) -> BrowserViewerTicket:
        try:
            async with self.engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT s.task_id, s.authorization_id, a.id AS attempt_id, "
                                "z.expires_at AS authorization_expires_at "
                                "FROM browser.sessions s "
                                "JOIN career.execution_tasks t ON t.id=s.task_id "
                                "AND t.user_id=s.user_id "
                                "JOIN career.boss_connections c ON c.id=t.connection_id "
                                "AND c.user_id=s.user_id AND c.status NOT IN ('revoked','failed') "
                                "JOIN career.execution_authorizations z ON z.id=s.authorization_id "
                                "AND z.task_id=t.id AND z.user_id=s.user_id "
                                "JOIN career.execution_attempts a ON a.task_id=t.id "
                                "AND a.authorization_id=z.id AND a.user_id=s.user_id "
                                "AND a.browser_session_id=s.session_id "
                                "JOIN browser.steel_operations o ON o.session_id=s.session_id "
                                "AND o.state='live' "
                                "WHERE s.session_id=:session_id AND s.user_id=:user_id "
                                "AND s.revoked=false AND z.status='active' "
                                "AND z.expires_at>clock_timestamp() AND z.scope='boss.login' "
                                "AND t.kind='boss_login' AND t.status='waiting' "
                                "AND c.browser_session_id=s.session_id "
                                "AND c.status='waiting_for_login' "
                                "AND a.status='waiting' AND a.outcome='browser_created'"
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
        expires_at = min(
            datetime.fromtimestamp(issued_at + 60, UTC), row["authorization_expires_at"]
        )
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
            attempt_id=row["attempt_id"],
            request_id=request_id,
            owner_id="viewer",
        )
        try:
            token = self.signer.sign(context, "viewer")
        except BrowserControlRejected:
            raise BrowserViewerTicketRejected("Browser session is not available") from None
        except (ValueError, TypeError):
            raise BrowserViewerTicketUnavailable(
                "Browser viewer authorization is unavailable"
            ) from None
        return BrowserViewerTicket(session_id, token, expires_at)
