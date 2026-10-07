from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Response
from pydantic import AnyHttpUrl
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

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
    fetch_viewer_document,
    validate_origin,
    viewer_context,
)


def create_app(
    *,
    verifier: CommandVerifier | None = None,
    store: PostgresLeaseStore | None = None,
    steel_client: httpx.AsyncClient | None = None,
    viewer_public_origin: AnyHttpUrl | None = None,
) -> FastAPI:
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
        except LeaseNotFound:
            raise HTTPException(403, "Browser command rejected") from None
        except ViewerRejected:
            raise HTTPException(502, "Viewer document unavailable") from None
        except (DBAPIError, PoolTimeoutError):
            raise HTTPException(503, "Browser coordination unavailable") from None
        return Response(
            content=html,
            media_type="text/html",
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": "frame-ancestors 'self'",
            },
        )

    return app
