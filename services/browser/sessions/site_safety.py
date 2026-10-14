"""Durable site stop, configured by trusted code, never by page/model input.

No clear/expiry API: a new Profile, task or process cannot recover automation.
Human input and physical cleanup use the existing separate lease/lifecycle paths.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from services.browser.sessions.authentication import CommandRejected
from services.browser.sessions.context import SiteScope

RiskReason = Literal["denied", "challenge", "rate_limited", "abnormal"]
_REASONS = frozenset({"denied", "challenge", "rate_limited", "abnormal"})


class SiteRiskDetected(Exception):
    def __init__(self, reason: RiskReason) -> None:
        if reason not in _REASONS:
            raise ValueError("Unknown site risk reason")
        self.reason = reason
        super().__init__("Site risk requires human handling")


class SiteSafetyBlocked(CommandRejected):
    pass


class PostgresSiteSafetyStore:
    def __init__(self, engine: AsyncEngine, scope: SiteScope) -> None:
        self.engine = engine
        self.scope = scope

    async def _lock(
        self, connection: AsyncConnection, session_id: UUID, user_id: str | None
    ) -> RowMapping:
        # Do not lock a session here: callers may already hold its executor lease
        # lock. The site row always serializes cross-session automatic actions.
        owner = await connection.scalar(
            text("SELECT user_id FROM browser.sessions WHERE session_id=:session"),
            {"session": session_id},
        )
        if owner is None or (user_id is not None and owner != user_id):
            raise CommandRejected("Site protection requires its registered session owner")
        params = {"user": owner, "site": self.scope.site}
        await connection.execute(
            text(
                "INSERT INTO browser.site_safety (user_id, site) VALUES (:user, :site) "
                "ON CONFLICT (user_id, site) DO NOTHING"
            ),
            params,
        )
        return (
            (
                await connection.execute(
                    text(
                        "SELECT * FROM browser.site_safety "
                        "WHERE user_id=:user AND site=:site FOR UPDATE"
                    ),
                    params,
                )
            )
            .mappings()
            .one()
        )

    async def _stop(
        self, connection: AsyncConnection, row: RowMapping, session_id: UUID, reason: RiskReason
    ) -> None:
        # Retain first detection evidence. Repeated observations cannot reset the
        # stop or replace its original session with an unrelated recovery attempt.
        if not row["blocked"]:
            await connection.execute(
                text(
                    "UPDATE browser.site_safety SET blocked=true, reason=:reason, "
                    "session_id=:session, stopped_at=clock_timestamp() "
                    "WHERE user_id=:user AND site=:site"
                ),
                {
                    "user": row["user_id"],
                    "site": self.scope.site,
                    "session": session_id,
                    "reason": reason,
                },
            )

    async def record_stop(self, session_id: UUID, reason: RiskReason) -> None:
        if reason not in _REASONS:
            raise ValueError("Unknown site risk reason")
        async with self.engine.begin() as connection:
            row = await self._lock(connection, session_id, None)
            await self._stop(connection, row, session_id, reason)

    @asynccontextmanager
    async def action_guard(
        self, session_id: UUID, user_id: str | None = None
    ) -> AsyncIterator[None]:
        """Compose inside the existing executor_action_guard, never instead of it.

        A detected risk commits before it is reported. Exceptions outside this
        exact typed signal never erase an existing stop or count as safe recovery.
        """
        detected: SiteRiskDetected | None = None
        async with self.engine.begin() as connection:
            row = await self._lock(connection, session_id, user_id)
            if row["blocked"]:
                raise SiteSafetyBlocked("Site automation is stopped pending human revalidation")
            try:
                yield
            except SiteRiskDetected as failure:
                await self._stop(connection, row, session_id, failure.reason)
                detected = failure
        if detected is not None:
            raise detected
