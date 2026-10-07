from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import AnyHttpUrl

from services.browser.app.factory import create_app
from services.browser.sessions.authentication import (
    BrowserCommand,
    CommandRejected,
    CommandVerifier,
)
from services.browser.sessions.postgres import PostgresLeaseStore


class _Engine:
    async def dispose(self) -> None:
        return None


class _ViewerStore:
    engine = _Engine()

    def __init__(self, reject: bool = False) -> None:
        self.reject = reject
        self.commands: list[BrowserCommand] = []

    async def authorize_viewer(self, command: BrowserCommand) -> None:
        if self.reject:
            raise CommandRejected("revoked")
        self.commands.append(command)


def _token(private_key: Ed25519PrivateKey, session_id: UUID) -> str:
    now = int(datetime.now(UTC).timestamp())
    return jwt.encode(
        {
            "iss": "careeract-api",
            "aud": "careeract-browser",
            "sub": "synthetic-user",
            "iat": now,
            "exp": now + 60,
            "jti": str(uuid4()),
            "session_id": str(session_id),
            "task_id": str(uuid4()),
            "authorization_id": str(uuid4()),
            "attempt_id": str(uuid4()),
            "request_id": str(uuid4()),
            "owner_id": "viewer",
            "action": "viewer",
        },
        private_key,
        algorithm="EdDSA",
    )


def _steel_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="http://steel:3000",
        transport=httpx.MockTransport(handler),
    )


def _app(
    private_key: Ed25519PrivateKey,
    store: _ViewerStore,
    client: httpx.AsyncClient,
) -> FastAPI:
    return create_app(
        verifier=CommandVerifier(private_key.public_key()),
        store=cast(PostgresLeaseStore, store),
        steel_client=client,
        viewer_public_origin=AnyHttpUrl("https://careeract.example"),
    )


def test_viewer_route_rewrites_steel_html_and_sets_browser_headers() -> None:
    session_id = uuid4()
    page_id = "page-a"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/sessions/debug"
        assert request.url.params["pageId"] == page_id
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text='<script>const ws="ws://steel:3000/v1/sessions/cast?pageId=page-a"</script>',
        )

    private_key = Ed25519PrivateKey.generate()
    store = _ViewerStore()
    steel_client = _steel_client(handler)
    with TestClient(_app(private_key, store, steel_client)) as client:
        response = client.get(
            f"/internal/v1/sessions/{session_id}/viewer",
            params={"pageId": page_id},
            headers={
                "Authorization": "Bearer " + _token(private_key, session_id),
                "Origin": "https://careeract.example",
            },
        )

    assert response.status_code == 200
    assert "/api/browser/sessions/" + str(session_id) + "/cast" in response.text
    assert "steel:3000" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"] == "frame-ancestors 'self'"
    assert len(store.commands) == 1


def test_viewer_route_rejects_wrong_origin_before_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Steel must not be contacted for a rejected origin")

    session_id = uuid4()
    private_key = Ed25519PrivateKey.generate()
    with TestClient(_app(private_key, _ViewerStore(), _steel_client(handler))) as client:
        response = client.get(
            f"/internal/v1/sessions/{session_id}/viewer?pageId=page-a",
            headers={
                "Authorization": "Bearer " + _token(private_key, session_id),
                "Origin": "https://evil.example",
            },
        )

    assert response.status_code == 403


def test_viewer_route_rejects_revoked_session() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Steel must not be contacted for a revoked session")

    session_id = uuid4()
    private_key = Ed25519PrivateKey.generate()
    with TestClient(_app(private_key, _ViewerStore(reject=True), _steel_client(handler))) as client:
        response = client.get(
            f"/internal/v1/sessions/{session_id}/viewer?pageId=page-a",
            headers={
                "Authorization": "Bearer " + _token(private_key, session_id),
                "Origin": "https://careeract.example",
            },
        )

    assert response.status_code == 403


def test_viewer_route_hides_invalid_steel_document() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://internal.example"})

    session_id = uuid4()
    private_key = Ed25519PrivateKey.generate()
    with TestClient(_app(private_key, _ViewerStore(), _steel_client(handler))) as client:
        response = client.get(
            f"/internal/v1/sessions/{session_id}/viewer?pageId=page-a",
            headers={
                "Authorization": "Bearer " + _token(private_key, session_id),
                "Origin": "https://careeract.example",
            },
        )

    assert response.status_code == 502
    assert "internal.example" not in response.text
