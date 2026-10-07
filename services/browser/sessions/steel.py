import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

import httpx
from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from services.browser.sessions.context import (
    BrowserContext,
    BrowserContextRejected,
    SiteScope,
)

SteelStatus = Literal["idle", "live", "released", "failed"]


class BrowserStateReader(Protocol):
    async def storage_state(self) -> object: ...


class SteelSessionConflict(Exception):
    pass


class SteelSessionUncertain(Exception):
    pass


class SteelSessionUnavailable(Exception):
    pass


class SessionResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    id: UUID
    status: SteelStatus


class SessionsResponse(BaseModel):
    sessions: list[SessionResponse]


class ReleaseResponse(SessionResponse):
    success: bool


@dataclass(frozen=True, slots=True)
class SteelSession:
    session_id: UUID
    status: SteelStatus


class SteelSessionManager:
    def __init__(self, client: httpx.AsyncClient, engine: AsyncEngine) -> None:
        origin = client.base_url
        if (
            origin.scheme not in ("http", "https")
            or not origin.host
            or origin.username
            or origin.password
            or origin.path != "/"
            or origin.query
            or origin.fragment
        ):
            raise ValueError("Steel requires an internal HTTP origin")
        self._client = client
        self._engine = engine

    @asynccontextmanager
    async def _exclusive(self) -> AsyncIterator[AsyncConnection]:
        try:
            async with self._engine.begin() as connection:
                await connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                await connection.execute(
                    text("SELECT pg_advisory_xact_lock(1937007980, 1)"),
                )
                yield connection
        except (DBAPIError, PoolTimeoutError):
            raise SteelSessionUncertain("Steel coordination requires reconciliation") from None

    async def _request(
        self, method: str, path: str, *, body: dict[str, object] | None = None
    ) -> httpx.Response:
        try:
            return await self._client.request(
                method, path, json=body, timeout=40, follow_redirects=False
            )
        except httpx.TransportError:
            raise SteelSessionUncertain(
                "Steel response unavailable; reconcile before retry"
            ) from None

    async def _sessions(self) -> list[SessionResponse]:
        response = await self._request("GET", "/v1/sessions")
        if response.status_code != 200:
            raise SteelSessionUnavailable("Steel inventory unavailable")
        try:
            sessions = SessionsResponse.model_validate_json(response.content).sessions
        except ValidationError:
            raise SteelSessionUnavailable("Steel inventory invalid") from None
        identifiers = [session.id for session in sessions]
        active = [session for session in sessions if session.status in ("live", "idle")]
        if len(set(identifiers)) != len(identifiers) or len(active) != 1:
            raise SteelSessionUnavailable("Steel inventory is ambiguous")
        return sessions

    async def inspect(self, session_id: UUID) -> SteelSession | None:
        async with self._exclusive():
            sessions = await self._sessions()
            session = next((session for session in sessions if session.id == session_id), None)
            return None if session is None else SteelSession(session.id, session.status)

    async def export_context(
        self, session_id: UUID, scope: SiteScope, *, browser_context: BrowserStateReader
    ) -> BrowserContext:
        async with self._exclusive() as connection:
            state = await connection.scalar(
                text("SELECT state FROM browser.steel_operations WHERE session_id=:session_id"),
                {"session_id": session_id},
            )
            if state != "live":
                raise SteelSessionConflict("Steel context is unowned or requires reconciliation")
            await self._confirm(session_id, "live")
            try:
                snapshot = await asyncio.wait_for(browser_context.storage_state(), timeout=10)
                context = BrowserContext.from_playwright(snapshot, scope)
            except (PlaywrightError, TimeoutError, BrowserContextRejected):
                raise SteelSessionUnavailable(
                    "Steel context is invalid or outside its scope"
                ) from None
            await self._confirm(session_id, "live")
            return context

    async def create(
        self, session_id: UUID, *, context: BrowserContext | None = None
    ) -> SteelSession:
        body: dict[str, object] = {"sessionId": str(session_id)}
        if context is not None:
            context.encode()
            body["sessionContext"] = context.to_steel()
        async with self._exclusive() as connection:
            reserved = await connection.scalar(
                text(
                    "SELECT session_id FROM browser.steel_operations "
                    "WHERE state <> 'released' OR session_id = :session_id LIMIT 1"
                ),
                {"session_id": session_id},
            )
            if reserved is not None:
                raise SteelSessionConflict("Steel lifecycle is reserved; reconcile before reuse")
            sessions = await self._sessions()
            if any(session.id == session_id or session.status == "live" for session in sessions):
                raise SteelSessionConflict("Existing Steel session must be reconciled")
            await connection.execute(
                text(
                    "INSERT INTO browser.steel_operations (session_id, state) "
                    "VALUES (:session_id, 'creating')"
                ),
                {"session_id": session_id},
            )
        response = await self._request("POST", "/v1/sessions", body=body)
        if response.status_code != 200:
            raise SteelSessionUncertain("Steel creation result unconfirmed")
        try:
            created = SessionResponse.model_validate_json(response.content)
        except ValidationError:
            raise SteelSessionUncertain("Steel creation response invalid") from None
        if created.id != session_id or created.status != "live":
            raise SteelSessionUncertain("Steel creation response does not match request")
        await self._confirm(session_id, "live")
        await self._transition(session_id, "creating", "live")
        return SteelSession(session_id, "live")

    async def release(self, session_id: UUID) -> SteelSession:
        async with self._exclusive() as connection:
            state = await connection.scalar(
                text("SELECT state FROM browser.steel_operations WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
            if state == "released":
                return SteelSession(session_id, "released")
            if state != "live":
                raise SteelSessionConflict("Steel session is unowned or requires reconciliation")
            sessions = await self._sessions()
            target = next((session for session in sessions if session.id == session_id), None)
            if target is None or target.status != "live":
                raise SteelSessionConflict("Requested Steel session is not active")
            await connection.execute(
                text(
                    "UPDATE browser.steel_operations SET state = 'releasing', "
                    "updated_at = clock_timestamp() WHERE session_id = :session_id"
                ),
                {"session_id": session_id},
            )
        response = await self._request("POST", f"/v1/sessions/{session_id}/release")
        if response.status_code != 200:
            raise SteelSessionUncertain("Steel release result unconfirmed")
        try:
            released = ReleaseResponse.model_validate_json(response.content)
        except ValidationError:
            raise SteelSessionUncertain("Steel release response invalid") from None
        if released.id != session_id or released.status != "released" or not released.success:
            raise SteelSessionUncertain("Steel release response does not match request")
        await self._confirm(session_id, "released")
        await self._transition(session_id, "releasing", "released")
        return SteelSession(session_id, "released")

    async def _transition(self, session_id: UUID, previous: str, current: str) -> None:
        async with self._exclusive() as connection:
            updated = await connection.scalar(
                text(
                    "UPDATE browser.steel_operations SET state = :current, "
                    "updated_at = clock_timestamp() "
                    "WHERE session_id = :session_id AND state = :previous RETURNING session_id"
                ),
                {"session_id": session_id, "previous": previous, "current": current},
            )
            if updated is None:
                raise SteelSessionUncertain("Steel reservation changed; reconciliation required")

    async def _confirm(self, session_id: UUID, status: SteelStatus) -> None:
        try:
            sessions = await self._sessions()
        except SteelSessionUnavailable:
            raise SteelSessionUncertain("Steel state readback unavailable") from None
        if not any(session.id == session_id and session.status == status for session in sessions):
            raise SteelSessionUncertain("Steel state readback does not confirm the operation")
