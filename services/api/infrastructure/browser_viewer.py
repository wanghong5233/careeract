from datetime import UTC, datetime
from uuid import UUID

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
                                "WHERE s.session_id=:session_id AND s.user_id=:user_id "
                                "AND s.revoked=false AND z.status='active' "
                                "AND z.expires_at>clock_timestamp() AND z.scope='boss.login' "
                                "AND t.kind='boss_login' AND t.status='waiting' "
                                "AND a.status='waiting' AND a.outcome='browser_registered'"
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
