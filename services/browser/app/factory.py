import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Response, WebSocket
from fastapi.responses import JSONResponse
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
    LifecycleAction,
    SessionAction,
)
from services.browser.sessions.execution import ExecutorLifecycle, ExecutorUnavailable
from services.browser.sessions.lease import LeaseConflict, LeaseNotFound, SessionLease
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.sessions.profiles import (
    BrowserProfileConflict,
    BrowserProfileUnavailable,
)
from services.browser.sessions.site_lifecycle import SiteLifecycleUnavailable, SiteSessionLifecycle
from services.browser.sessions.steel import (
    SteelSessionConflict,
    SteelSessionManager,
    SteelSessionUnavailable,
    SteelSessionUncertain,
)
from services.browser.sessions.viewer import (
    ViewerRejected,
    cast_websocket_url,
    fetch_viewer_document,
    resolve_viewer_page,
    validate_origin,
    validate_page_id,
    viewer_context,
    viewer_cookie_name,
)
from services.browser.site_adapters.boss import BossReadOnlyPage
from services.browser.site_adapters.boss_context import (
    BossContextReader,
    BossContextUnavailable,
    BossDisconnectUnconfirmed,
)


class ViewerAuthorizationRevoked(Exception):
    pass


class ViewerCoordinationUnavailable(Exception):
    pass


@dataclass
class _ActiveViewer:
    command: BrowserCommand
    lease_id: UUID | None


async def _relay_websocket(
    websocket: WebSocket,
    upstream: Any,
    *,
    authorization_check: Callable[[], Awaitable[None]],
    authorization_renew: Callable[[], Awaitable[None]],
    authorization_interval: float = 5.0,
    allow_input: bool = True,
    input_guard: Callable[[], AbstractAsyncContextManager[None]] | None = None,
) -> None:
    if allow_input and input_guard is None:
        raise ValueError("Interactive relay requires an input guard")

    async def from_client() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            try:
                async with asyncio.timeout(5):
                    if not allow_input:
                        await authorization_check()
                        raise ViewerAuthorizationRevoked
                    assert input_guard is not None
                    async with input_guard():
                        if message.get("text") is not None:
                            await upstream.send(message["text"])
                        elif message.get("bytes") is not None:
                            await upstream.send(message["bytes"])
            except (CommandRejected, LeaseNotFound, LeaseConflict) as error:
                raise ViewerAuthorizationRevoked from error
            except (DBAPIError, PoolTimeoutError, TimeoutError) as error:
                raise ViewerCoordinationUnavailable from error

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
    steel_sessions: SteelSessionManager | None = None,
    viewer_public_origin: AnyHttpUrl | None = None,
    steel_ws_connect: Callable[..., Any] | None = None,
    viewer_authorization_interval: float = 5.0,
    site_lifecycles: Mapping[str, SiteSessionLifecycle] | None = None,
    context_reader: Callable[[UUID], BossContextReader] | None = None,
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
    active_viewers: dict[UUID, _ActiveViewer] = {}
    active_watchers: dict[UUID, dict[UUID, _ActiveViewer]] = {}

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
            if action == "block_viewer":
                await store.wait_for_viewer_stop(command)
        except CommandRejected:
            raise HTTPException(403, "Browser command rejected") from None
        except LeaseConflict:
            raise HTTPException(409, "Browser session conflict") from None
        except (DBAPIError, PoolTimeoutError):
            raise HTTPException(503, "Browser coordination unavailable") from None

    @app.post("/internal/v1/sessions/{session_id}/lifecycle/{action}")
    async def lifecycle_command(
        session_id: UUID,
        action: LifecycleAction,
        authorization: str = Header(default=""),
    ) -> dict[str, str | bool]:
        command = authenticate(session_id, action, authorization)
        if steel_sessions is None or store is None:
            raise HTTPException(503, "Browser lifecycle is not configured")
        try:
            site = site_lifecycles.get(command.owner_id) if site_lifecycles is not None else None
            if site_lifecycles is not None and (site is None or action not in site.actions):
                raise CommandRejected("Site lifecycle action is not configured")
            if action in {"finish", "forget"} and site is None:
                raise CommandRejected("Site profile action is not configured")
            login_verified = False
            if action in ("release", "finish"):
                await store.wait_for_viewer_stop(command)
            await store.authorize_lifecycle(command)
            async with store.lifecycle_guard(command):
                restored = (
                    await site.restore(command.sub)
                    if action == "create" and site is not None
                    else None
                )
                if action == "create":
                    session = await steel_sessions.create(session_id, context=restored)
                elif action == "forget":
                    session = await steel_sessions.release(session_id)
                    if site is None:
                        raise CommandRejected("Profile removal is not configured")
                    await site.forget(command.sub, session_id)
                else:
                    if action == "finish":
                        if site is not None:
                            physical = await steel_sessions.inspect(session_id)
                            if physical is None or physical.status != "live":
                                raise SteelSessionConflict(
                                    "Login verification requires a live session"
                                )
                            login_verified = await site.save(command.sub, session_id)
                        session = await steel_sessions.release(session_id)
                        if not command.is_current(datetime.now(UTC).timestamp()):
                            raise CommandRejected("Login verification authorization expired")
                    else:
                        try:
                            if site is not None:
                                physical = await steel_sessions.inspect(session_id)
                                if physical is not None and physical.status == "live":
                                    login_verified = await site.save(command.sub, session_id)
                        finally:
                            session = await steel_sessions.release(session_id)
                if action == "create" and site is not None:
                    if not command.is_current(datetime.now(UTC).timestamp()):
                        raise CommandRejected("Login navigation authorization expired")
                    await site.prepare(session_id)
        except CommandRejected:
            raise HTTPException(403, "Browser lifecycle rejected") from None
        except (LeaseNotFound, LeaseConflict, SteelSessionConflict) as failure:
            logging.getLogger(__name__).warning(
                "Browser lifecycle conflict session=%s action=%s boundary=%s reason=%s",
                session_id,
                action,
                type(failure).__name__,
                str(failure),
            )
            raise HTTPException(409, "Browser lifecycle conflict") from None
        except (
            DBAPIError,
            PoolTimeoutError,
            SteelSessionUnavailable,
            SteelSessionUncertain,
            BrowserProfileUnavailable,
            BrowserProfileConflict,
            SiteLifecycleUnavailable,
        ) as failure:
            logging.getLogger(__name__).warning(
                "Browser lifecycle unavailable session=%s action=%s boundary=%s",
                session_id,
                action,
                type(failure).__name__,
            )
            raise HTTPException(503, "Browser coordination unavailable") from None
        result: dict[str, str | bool] = {
            "session_id": str(session.session_id),
            "status": session.status,
        }
        if action == "finish":
            result["login_verified"] = login_verified
        return result

    @app.post("/internal/v1/sessions/{session_id}/boss/page")
    async def read_boss_page(session_id: UUID, authorization: str = Header(default="")) -> Response:
        command = authenticate(session_id, "snapshot", authorization)
        if command.owner_id != "boss-page-reader":
            raise HTTPException(403, "Browser page read rejected")
        if context_reader is None or store is None:
            raise HTTPException(503, "Browser page reader is not configured")
        try:
            async with store.snapshot_guard(command):
                result = await context_reader(session_id).read_page()
        except CommandRejected:
            raise HTTPException(403, "Browser page read rejected") from None
        except (LeaseNotFound, LeaseConflict):
            raise HTTPException(409, "Browser page read conflicts with session state") from None
        except (DBAPIError, PoolTimeoutError, BossContextUnavailable) as failure:
            logging.getLogger(__name__).warning(
                "BOSS page read unavailable session=%s boundary=%s",
                session_id,
                type(failure).__name__,
            )
            raise HTTPException(503, "Browser page read unavailable") from None
        return JSONResponse(
            {"session_id": str(session_id), "page": asdict(result)},
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/internal/v1/sessions/{session_id}/boss/{action}")
    async def read_boss_conversation(
        session_id: UUID,
        action: Literal["conversation", "observe_conversation"],
        authorization: str = Header(default=""),
    ) -> Response:
        command = authenticate(session_id, action, authorization)
        if command.owner_id != "boss-page-reader" or command.conversation_id is None:
            raise HTTPException(403, "Conversation read rejected")
        if context_reader is None or store is None:
            raise HTTPException(503, "Browser reader is not configured")
        try:
            lease = await store.execute(command.model_copy(update={"action": "acquire"}))
            check = command.model_copy(update={"action": "check", "lease_id": lease.lease_id})

            async def check_lease() -> None:
                await store.execute(check)

            async def drain() -> None:
                await store.execute(check.model_copy(update={"action": "stop", "jti": uuid4()}))

            async def disconnected() -> None:
                pass

            async def release() -> None:
                await store.confirm_stopped(session_id, lease.lease_id)

            lifecycle = ExecutorLifecycle(
                check_lease=check_lease,
                mark_draining=drain,
                disconnect=disconnected,
                release=release,
            )

            async def observe() -> BossReadOnlyPage | None:
                async with store.executor_action_guard(check):
                    try:
                        reader = context_reader(session_id)
                        if action == "observe_conversation":
                            return await reader.read_conversation(
                                command.conversation_id or "", navigate=False
                            )
                        return await reader.read_conversation(command.conversation_id or "")
                    except BossDisconnectUnconfirmed:
                        raise
                    except BossContextUnavailable:
                        return None

            result = await lifecycle.run(observe)
            await lifecycle.stop()
            if result is None:
                raise HTTPException(503, "Conversation observation unavailable")
        except CommandRejected:
            raise HTTPException(403, "Conversation authorization rejected") from None
        except (LeaseNotFound, LeaseConflict):
            raise HTTPException(409, "Conversation control requires reconciliation") from None
        except (DBAPIError, PoolTimeoutError, BossContextUnavailable, ExecutorUnavailable):
            raise HTTPException(503, "Conversation execution requires reconciliation") from None
        return JSONResponse(
            {"session_id": str(session_id), "page": asdict(result)},
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/internal/v1/sessions/{session_id}/viewer")
    async def viewer_document(
        session_id: UUID,
        page_id: str | None = Query(default=None, alias="pageId"),
        mode: Literal["control", "watch"] = Query(default="control"),
        origin: str | None = Header(default=None),
        authorization: str = Header(default=""),
    ) -> Response:
        action: Action = "watcher" if mode == "watch" else "viewer"
        command = authenticate(session_id, action, authorization)
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
            if command.action == "watcher":
                await store.authorize_watcher(command)
            else:
                await store.authorize_viewer(command)
            page_id = await resolve_viewer_page(steel_client, session_id, page_id)
            html = await fetch_viewer_document(
                steel_client,
                page_id,
                context,
                interactive=command.action == "viewer",
                renewal_mode="watch" if command.action == "watcher" else "control",
            )
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
            key=viewer_cookie_name(
                session_id, "watch" if command.action == "watcher" else "control"
            ),
            value=viewer_token,
            max_age=60,
            httponly=True,
            samesite="strict",
            secure=context.origin.startswith("https://"),
            path="/",
        )
        return response

    @app.post("/internal/v1/sessions/{session_id}/viewer/renew", status_code=204)
    async def renew_viewer_ticket(
        session_id: UUID,
        mode: Literal["control", "watch"] = Query(default="control"),
        authorization: str = Header(default=""),
    ) -> None:
        action: Action = "watcher" if mode == "watch" else "viewer"
        command = authenticate(session_id, action, authorization)
        if action == "watcher":
            active_watchers_for_session = active_watchers.get(session_id, {})
            matching = [
                watcher
                for watcher in active_watchers_for_session.values()
                if all(
                    getattr(watcher.command, field) == getattr(command, field)
                    for field in ("sub", "task_id", "authorization_id", "attempt_id", "owner_id")
                )
                and command.exp >= watcher.command.exp
            ]
            if not matching:
                raise HTTPException(409, "Viewer connection is not active in this process")
            assert store is not None
            try:
                await store.authorize_watcher(command)
            except (CommandRejected, LeaseConflict, LeaseNotFound):
                raise HTTPException(403, "Viewer renewal rejected") from None
            except (DBAPIError, PoolTimeoutError):
                raise HTTPException(503, "Viewer coordination unavailable") from None
            for watcher in matching:
                watcher.command = command
            return

        control_active = active_viewers.get(session_id)
        if control_active is None or control_active.lease_id is None:
            raise HTTPException(409, "Viewer connection is not active in this process")
        previous = control_active.command
        if (
            any(
                getattr(previous, field) != getattr(command, field)
                for field in ("sub", "task_id", "authorization_id", "attempt_id", "owner_id")
            )
            or command.exp < previous.exp
        ):
            raise HTTPException(403, "Viewer renewal rejected")
        assert store is not None
        try:
            await store.refresh_viewer(command, control_active.lease_id)
        except (CommandRejected, LeaseConflict, LeaseNotFound):
            raise HTTPException(403, "Viewer renewal rejected") from None
        except (DBAPIError, PoolTimeoutError):
            raise HTTPException(503, "Viewer coordination unavailable") from None
        control_active.command = command

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
            mode = websocket.query_params.get("mode", "control")
            if mode not in ("control", "watch"):
                raise ViewerRejected("Viewer mode is invalid")
            action: Action = "watcher" if mode == "watch" else "viewer"
            token = websocket.cookies.get(viewer_cookie_name(session_id, mode))
            if not token:
                raise ViewerRejected("Viewer command required")
            command = verifier.verify(token, session_id, action)
            page_id = validate_page_id(websocket.query_params.get("pageId"))
            if page_id is None or set(websocket.query_params) - {"pageId", "sessionId", "mode"}:
                raise ViewerRejected("Viewer requires one selected page")
            page_id = await resolve_viewer_page(steel_client, session_id, page_id)
            lease = None if command.action == "watcher" else await store.acquire_viewer(command)
        except (CommandRejected, ViewerRejected, LeaseNotFound, LeaseConflict):
            await websocket.close(code=1008)
            return
        except (DBAPIError, PoolTimeoutError):
            await websocket.close(code=1013)
            return

        upstream_url = cast_websocket_url(
            context,
            page_id,
            {"readOnly": "true"} if lease is None else None,
        )
        connector = steel_ws_connect or connect
        connection_id = uuid4()
        try:
            close_code = 1000
            async with connector(
                upstream_url,
                open_timeout=10,
                close_timeout=5,
                max_size=2 * 1024 * 1024,
            ) as upstream:
                try:
                    if lease is not None:
                        await store.renew_viewer(command, lease.lease_id)
                    else:
                        await store.authorize_watcher(command)
                    active = _ActiveViewer(command, lease.lease_id if lease is not None else None)
                    if lease is not None:
                        active_viewers[session_id] = active
                    else:
                        active_watchers.setdefault(session_id, {})[connection_id] = active
                    await websocket.accept()
                    if lease is not None:
                        lease_id = lease.lease_id
                        await _relay_websocket(
                            websocket,
                            upstream,
                            authorization_check=lambda: store.check_viewer(
                                active.command, lease_id
                            ),
                            authorization_renew=lambda: store.renew_viewer(
                                active.command, lease_id
                            ),
                            authorization_interval=viewer_authorization_interval,
                            allow_input=True,
                            input_guard=lambda: store.viewer_input_guard(active.command, lease_id),
                        )
                    else:
                        await _relay_websocket(
                            websocket,
                            upstream,
                            authorization_check=lambda: store.authorize_watcher(active.command),
                            authorization_renew=lambda: store.authorize_watcher(active.command),
                            authorization_interval=viewer_authorization_interval,
                            allow_input=False,
                        )
                except (ViewerAuthorizationRevoked, CommandRejected, LeaseNotFound, LeaseConflict):
                    close_code = 1008
                except (ViewerCoordinationUnavailable, DBAPIError, PoolTimeoutError):
                    close_code = 1013
                except (ConnectionClosed, WebSocketDisconnect, OSError, TimeoutError):
                    close_code = 1011
                finally:
                    if lease is not None:
                        active_viewers.pop(session_id, None)
                    else:
                        watchers = active_watchers.get(session_id)
                        if watchers is not None:
                            watchers.pop(connection_id, None)
                            if not watchers:
                                active_watchers.pop(session_id, None)
                    if lease is not None:
                        await store.drain_viewer(command, lease.lease_id)
            async with asyncio.timeout(5):
                await upstream.wait_closed()
            if lease is not None:
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
