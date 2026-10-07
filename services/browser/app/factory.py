import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Response, WebSocket
from pydantic import AnyHttpUrl
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.websockets import WebSocketDisconnect, WebSocketState
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from services.browser.sessions.authentication import (
    Action,
    BrowserCommand,
    CommandRejected,
    CommandVerifier,
    LeaseAction,
    SessionAction,
)
from services.browser.sessions.lease import LeaseConflict, LeaseNotFound, SessionLease
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.sessions.viewer import (
    ViewerRejected,
    cast_websocket_url,
    fetch_viewer_document,
    validate_origin,
    validate_page_id,
    viewer_context,
    viewer_cookie_name,
)


class ViewerAuthorizationRevoked(Exception):
    pass


class ViewerCoordinationUnavailable(Exception):
    pass


async def _relay_websocket(
    websocket: WebSocket,
    upstream: Any,
    *,
    authorization_check: Callable[[], Awaitable[None]],
    authorization_renew: Callable[[], Awaitable[None]],
    authorization_interval: float = 5.0,
) -> None:
    async def from_client() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            try:
                async with asyncio.timeout(5):
                    await authorization_check()
            except (CommandRejected, LeaseNotFound, LeaseConflict) as error:
                raise ViewerAuthorizationRevoked from error
            except (DBAPIError, PoolTimeoutError, TimeoutError) as error:
                raise ViewerCoordinationUnavailable from error
            if message.get("text") is not None:
                await upstream.send(message["text"])
            elif message.get("bytes") is not None:
                await upstream.send(message["bytes"])

    async def from_upstream() -> None:
        async for message in upstream:
            if isinstance(message, bytes):
                await websocket.send_bytes(message)
            else:
                await websocket.send_text(message)

    async def monitor_authorization() -> None:
        while True:
            await asyncio.sleep(authorization_interval)
            try:
                async with asyncio.timeout(5):
                    await authorization_renew()
            except (CommandRejected, LeaseNotFound, LeaseConflict) as error:
                raise ViewerAuthorizationRevoked from error
            except (DBAPIError, PoolTimeoutError, TimeoutError) as error:
                raise ViewerCoordinationUnavailable from error

    client_task = asyncio.create_task(from_client())
    upstream_task = asyncio.create_task(from_upstream())
    authorization_task = asyncio.create_task(monitor_authorization())
    tasks = (client_task, upstream_task, authorization_task)
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def create_app(
    *,
    verifier: CommandVerifier | None = None,
    store: PostgresLeaseStore | None = None,
    steel_client: httpx.AsyncClient | None = None,
    viewer_public_origin: AnyHttpUrl | None = None,
    steel_ws_connect: Callable[..., Any] | None = None,
    viewer_authorization_interval: float = 5.0,
) -> FastAPI:
    if not 0 < viewer_authorization_interval <= 5:
        raise ValueError("Viewer authorization interval must be within 5 seconds")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if store is not None:
                await store.engine.dispose()
            if steel_client is not None:
                await steel_client.aclose()

    app = FastAPI(title="CareerAct Browser Service", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    def authenticate(session_id: UUID, action: Action, authorization: str) -> BrowserCommand:
        if verifier is None or store is None:
            raise HTTPException(503, "Browser control is not configured")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Browser command required")
        try:
            return verifier.verify(token, session_id, action)
        except CommandRejected:
            raise HTTPException(403, "Browser command rejected") from None

    @app.post("/internal/v1/sessions/{session_id}/lease/{action}")
    async def lease_command(
        session_id: UUID, action: LeaseAction, authorization: str = Header(default="")
    ) -> SessionLease:
        command = authenticate(session_id, action, authorization)
        assert store is not None
        try:
            return await store.execute(command)
        except CommandRejected:
            raise HTTPException(403, "Browser command rejected") from None
        except LeaseNotFound:
            raise HTTPException(404, "Session lease not found") from None
        except LeaseConflict:
            raise HTTPException(409, "Session lease conflict") from None
        except (DBAPIError, PoolTimeoutError):
            raise HTTPException(503, "Browser coordination unavailable") from None

    @app.post("/internal/v1/sessions/{session_id}/{action}", status_code=204)
    async def session_command(
        session_id: UUID, action: SessionAction, authorization: str = Header(default="")
    ) -> None:
        command = authenticate(session_id, action, authorization)
        assert store is not None
        try:
            await store.manage(command)
        except CommandRejected:
            raise HTTPException(403, "Browser command rejected") from None
        except LeaseConflict:
            raise HTTPException(409, "Browser session conflict") from None
        except (DBAPIError, PoolTimeoutError):
            raise HTTPException(503, "Browser coordination unavailable") from None

    @app.get("/internal/v1/sessions/{session_id}/viewer")
    async def viewer_document(
        session_id: UUID,
        page_id: str = Query(alias="pageId"),
        origin: str | None = Header(default=None),
        authorization: str = Header(default=""),
    ) -> Response:
        command = authenticate(session_id, "viewer", authorization)
        if steel_client is None or viewer_public_origin is None:
            raise HTTPException(503, "Browser viewer is not configured")
        context = viewer_context(
            session_id=session_id,
            origin=viewer_public_origin,
            steel_origin=AnyHttpUrl(str(steel_client.base_url)),
        )
        try:
            validate_origin(context, origin)
        except ViewerRejected as error:
            raise HTTPException(403, str(error)) from None
        try:
            assert store is not None
            await store.authorize_viewer(command)
            html = await fetch_viewer_document(steel_client, page_id, context)
        except CommandRejected:
            raise HTTPException(403, "Browser command rejected") from None
        except (LeaseNotFound, LeaseConflict):
            raise HTTPException(403, "Browser command rejected") from None
        except ViewerRejected:
            raise HTTPException(502, "Viewer document unavailable") from None
        except (DBAPIError, PoolTimeoutError):
            raise HTTPException(503, "Browser coordination unavailable") from None
        response = Response(
            content=html,
            media_type="text/html",
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": "frame-ancestors 'self'",
            },
        )
        _, _, viewer_token = authorization.partition(" ")
        response.set_cookie(
            key=viewer_cookie_name(session_id),
            value=viewer_token,
            max_age=60,
            httponly=True,
            samesite="strict",
            secure=context.origin.startswith("https://"),
            path="/",
        )
        return response

    @app.websocket("/internal/v1/sessions/{session_id}/cast")
    async def viewer_cast(websocket: WebSocket, session_id: UUID) -> None:
        if (
            verifier is None
            or store is None
            or steel_client is None
            or viewer_public_origin is None
        ):
            await websocket.close(code=1013)
            return
        context = viewer_context(
            session_id=session_id,
            origin=viewer_public_origin,
            steel_origin=AnyHttpUrl(str(steel_client.base_url)),
        )
        try:
            validate_origin(context, websocket.headers.get("origin"))
            token = websocket.cookies.get(viewer_cookie_name(session_id))
            if not token:
                raise ViewerRejected("Viewer command required")
            command = verifier.verify(token, session_id, "viewer")
            page_id = validate_page_id(websocket.query_params.get("pageId", ""))
            lease = await store.acquire_viewer(command)
        except (CommandRejected, ViewerRejected, LeaseNotFound, LeaseConflict):
            await websocket.close(code=1008)
            return
        except (DBAPIError, PoolTimeoutError):
            await websocket.close(code=1013)
            return

        upstream_url = cast_websocket_url(context, page_id)
        connector = steel_ws_connect or connect
        try:
            close_code = 1000
            async with connector(
                upstream_url,
                open_timeout=10,
                close_timeout=5,
                max_size=2 * 1024 * 1024,
            ) as upstream:
                try:
                    await store.renew_viewer(command, lease.lease_id)
                    await websocket.accept()
                    await _relay_websocket(
                        websocket,
                        upstream,
                        authorization_check=lambda: store.check_viewer(command, lease.lease_id),
                        authorization_renew=lambda: store.renew_viewer(command, lease.lease_id),
                        authorization_interval=viewer_authorization_interval,
                    )
                except (ViewerAuthorizationRevoked, CommandRejected, LeaseNotFound, LeaseConflict):
                    close_code = 1008
                except (ViewerCoordinationUnavailable, DBAPIError, PoolTimeoutError):
                    close_code = 1013
                except (ConnectionClosed, WebSocketDisconnect, OSError, TimeoutError):
                    close_code = 1011
                finally:
                    await store.drain_viewer(command, lease.lease_id)
            async with asyncio.timeout(5):
                await upstream.wait_closed()
            await store.confirm_stopped(session_id, lease.lease_id)
            if websocket.application_state != WebSocketState.DISCONNECTED:
                await websocket.close(code=close_code)
        except (DBAPIError, PoolTimeoutError):
            if websocket.application_state != WebSocketState.DISCONNECTED:
                await websocket.close(code=1013)
        except (LeaseConflict, LeaseNotFound, CommandRejected):
            if websocket.application_state != WebSocketState.DISCONNECTED:
                await websocket.close(code=1008)
        except (ConnectionClosed, WebSocketDisconnect, OSError, TimeoutError):
            if websocket.application_state != WebSocketState.DISCONNECTED:
                await websocket.close(code=1011)
        except asyncio.CancelledError:
            raise
        except RuntimeError:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.close(code=1011)

    return app
