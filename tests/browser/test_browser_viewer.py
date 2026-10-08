import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import AnyHttpUrl
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.websockets import WebSocketDisconnect

from services.browser.app.factory import create_app
from services.browser.sessions.authentication import (
    BrowserCommand,
    CommandRejected,
    CommandVerifier,
)
from services.browser.sessions.lease import SessionLease
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.sessions.viewer import viewer_cookie_name


class _Engine:
    async def dispose(self) -> None:
        return None


class _ViewerStore:
    engine = _Engine()

    def __init__(self, reject: bool = False, reject_after: int | None = None) -> None:
        self.reject = reject
        self.reject_after = reject_after
        self.calls = 0
        self.commands: list[BrowserCommand] = []
        self.drained = False
        self.released = False

    async def authorize_viewer(self, command: BrowserCommand) -> None:
        self.calls += 1
        if self.reject or (self.reject_after is not None and self.calls > self.reject_after):
            raise CommandRejected("revoked")
        self.commands.append(command)

    async def acquire_viewer(self, command: BrowserCommand) -> SessionLease:
        await self.authorize_viewer(command)
        return SessionLease(command.session_id, uuid4(), command.owner_id, datetime.now(UTC))

    async def renew_viewer(self, command: BrowserCommand, lease_id: UUID) -> None:
        await self.authorize_viewer(command)

    async def check_viewer(self, command: BrowserCommand, lease_id: UUID) -> None:
        await self.authorize_viewer(command)

    async def refresh_viewer(self, command: BrowserCommand, lease_id: UUID) -> None:
        await self.authorize_viewer(command)

    async def drain_viewer(self, command: BrowserCommand, lease_id: UUID) -> None:
        self.drained = True

    async def confirm_stopped(self, session_id: UUID, lease_id: UUID) -> None:
        assert self.drained
        self.released = True


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


def _steel_client(
    handler: Callable[[httpx.Request], httpx.Response], session_id: UUID | None = None
) -> httpx.AsyncClient:
    def handle(request: httpx.Request) -> httpx.Response:
        if session_id is not None and request.url.path == "/v1/sessions":
            return httpx.Response(
                200, json={"sessions": [{"id": str(session_id), "status": "live"}]}
            )
        if session_id is not None and request.url.path.endswith("/live-details"):
            return httpx.Response(200, json={"pages": [{"id": "page-a"}]})
        return handler(request)

    return httpx.AsyncClient(
        base_url="http://steel:3000",
        transport=httpx.MockTransport(handle),
    )


def _app(
    private_key: Ed25519PrivateKey,
    store: _ViewerStore,
    client: httpx.AsyncClient,
    connector: Callable[..., Any] | None = None,
    viewer_authorization_interval: float = 5.0,
) -> FastAPI:
    return create_app(
        verifier=CommandVerifier(private_key.public_key()),
        store=cast(PostgresLeaseStore, store),
        steel_client=client,
        viewer_public_origin=AnyHttpUrl("https://careeract.example"),
        steel_ws_connect=connector,
        viewer_authorization_interval=viewer_authorization_interval,
    )


def test_viewer_route_rewrites_steel_html_and_sets_browser_headers() -> None:
    session_id = uuid4()
    page_id = "page-a"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/sessions/debug"
        assert request.url.params["pageId"] == page_id
        assert request.url.params["interactive"] == "true"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text='<script>const ws="ws://steel:3000/v1/sessions/cast?pageId=page-a"</script>',
        )

    private_key = Ed25519PrivateKey.generate()
    store = _ViewerStore()
    steel_client = _steel_client(handler, session_id)
    with TestClient(_app(private_key, store, steel_client)) as client:
        response = client.get(
            f"/internal/v1/sessions/{session_id}/viewer",
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
    assert viewer_cookie_name(session_id) in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert len(store.commands) == 1


@pytest.mark.parametrize(
    "query", ["", "?tabInfo=true", "?pageId=page-a&tabInfo=true", "?pageIndex=1"]
)
def test_viewer_cast_rejects_multi_channel_and_unselected_requests(query: str) -> None:
    session_id = uuid4()
    private_key = Ed25519PrivateKey.generate()
    store = _ViewerStore()
    connector = _Connector(_Upstream())
    with (
        TestClient(
            _app(private_key, store, _steel_client(lambda _: httpx.Response(500)), connector)
        ) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            f"/internal/v1/sessions/{session_id}/cast{query}",
            headers={
                "Origin": "https://careeract.example",
                "Cookie": f"{viewer_cookie_name(session_id)}={_token(private_key, session_id)}",
            },
        ),
    ):
        pass
    assert store.calls == 0
    assert connector.url == ""


def test_viewer_route_rejects_wrong_origin_before_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Steel must not be contacted for a rejected origin")

    session_id = uuid4()
    private_key = Ed25519PrivateKey.generate()
    with TestClient(
        _app(private_key, _ViewerStore(), _steel_client(handler, session_id))
    ) as client:
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


class _Upstream:
    def __init__(self) -> None:
        self.sent: list[str | bytes] = []
        self._first = True
        self._stop = asyncio.Event()

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)
        self._stop.set()

    async def wait_closed(self) -> None:
        return None

    def __aiter__(self) -> "_Upstream":
        return self

    async def __anext__(self) -> str:
        if self._first:
            self._first = False
            return "from-steel"
        await self._stop.wait()
        raise StopAsyncIteration


class _Connector:
    def __init__(self, upstream: _Upstream, uncertain_close: bool = False) -> None:
        self.upstream = upstream
        self.url = ""
        self.uncertain_close = uncertain_close

    def __call__(self, url: str, **_: object) -> "_Connector":
        self.url = url
        return self

    async def __aenter__(self) -> _Upstream:
        return self.upstream

    async def __aexit__(self, *_: object) -> None:
        if self.uncertain_close:
            raise OSError("disconnect unconfirmed")
        return None


def test_viewer_cast_uses_cookie_ticket_and_rewrites_upstream_session() -> None:
    session_id = uuid4()
    private_key = Ed25519PrivateKey.generate()
    upstream = _Upstream()
    connector = _Connector(upstream)
    steel_client = _steel_client(
        lambda _: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text='<script>const ws="ws://steel:3000/v1/sessions/cast"</script>',
        ),
        session_id,
    )
    with (
        TestClient(_app(private_key, _ViewerStore(), steel_client, connector)) as client,
        client.websocket_connect(
            f"/internal/v1/sessions/{session_id}/cast?pageId=page-a",
            headers={
                "Origin": "https://careeract.example",
                "Cookie": f"{viewer_cookie_name(session_id)}={_token(private_key, session_id)}",
            },
        ) as socket,
    ):
        assert socket.receive_text() == "from-steel"
        socket.send_text("from-viewer")

    assert connector.url.endswith(f"/v1/sessions/cast?pageId=page-a&sessionId={session_id}")
    assert upstream.sent == ["from-viewer"]


def test_viewer_renewal_updates_active_channel_and_rejects_changed_scope() -> None:
    session_id = uuid4()
    private_key = Ed25519PrivateKey.generate()
    original = _token(private_key, session_id)
    payload = CommandVerifier(private_key.public_key()).verify(original, session_id, "viewer")
    renewed = jwt.encode(
        payload.model_dump(mode="json") | {"jti": str(uuid4())}, private_key, algorithm="EdDSA"
    )
    wrong_scope = jwt.encode(
        payload.model_dump(mode="json") | {"attempt_id": str(uuid4())},
        private_key,
        algorithm="EdDSA",
    )
    store = _ViewerStore()
    with TestClient(
        _app(
            private_key,
            store,
            _steel_client(lambda _: httpx.Response(500), session_id),
            _Connector(_Upstream()),
        )
    ) as client:
        renewal_url = f"/internal/v1/sessions/{session_id}/viewer/renew"
        assert (
            client.post(renewal_url, headers={"Authorization": "Bearer " + renewed}).status_code
            == 409
        )
        with client.websocket_connect(
            f"/internal/v1/sessions/{session_id}/cast?pageId=page-a",
            headers={
                "Origin": "https://careeract.example",
                "Cookie": f"{viewer_cookie_name(session_id)}={original}",
            },
        ) as socket:
            assert socket.receive_text() == "from-steel"
            assert (
                client.post(
                    renewal_url, headers={"Authorization": "Bearer " + wrong_scope}
                ).status_code
                == 403
            )
            assert (
                client.post(renewal_url, headers={"Authorization": "Bearer " + renewed}).status_code
                == 204
            )
            assert store.commands[-1].jti != payload.jti
            socket.send_text("finish")
    assert store.drained and store.released


def test_viewer_cast_rejects_missing_cookie() -> None:
    session_id = uuid4()
    private_key = Ed25519PrivateKey.generate()
    connector = _Connector(_Upstream())
    with (
        TestClient(
            _app(
                private_key, _ViewerStore(), _steel_client(lambda _: httpx.Response(500)), connector
            )
        ) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            f"/internal/v1/sessions/{session_id}/cast?pageId=page-a",
            headers={"Origin": "https://careeract.example"},
        ),
    ):
        pass

    assert connector.url == ""


def test_viewer_cast_closes_when_session_is_revoked_after_connect() -> None:
    session_id = uuid4()
    private_key = Ed25519PrivateKey.generate()
    upstream = _Upstream()
    connector = _Connector(upstream)
    store = _ViewerStore(reject_after=2)
    steel_client = _steel_client(lambda _: httpx.Response(500), session_id)
    with (
        TestClient(
            _app(
                private_key,
                store,
                steel_client,
                connector,
                viewer_authorization_interval=0.01,
            )
        ) as client,
        client.websocket_connect(
            f"/internal/v1/sessions/{session_id}/cast?pageId=page-a",
            headers={
                "Origin": "https://careeract.example",
                "Cookie": f"{viewer_cookie_name(session_id)}={_token(private_key, session_id)}",
            },
        ) as socket,
    ):
        assert socket.receive_text() == "from-steel"
        with pytest.raises(WebSocketDisconnect) as disconnected:
            socket.receive_text()
        assert disconnected.value.code == 1008
    assert store.drained and store.released


def test_viewer_cast_keeps_lease_when_upstream_disconnect_is_uncertain() -> None:
    session_id = uuid4()
    private_key = Ed25519PrivateKey.generate()
    store = _ViewerStore(reject_after=2)
    connector = _Connector(_Upstream(), uncertain_close=True)
    with (
        TestClient(
            _app(
                private_key,
                store,
                _steel_client(lambda _: httpx.Response(500), session_id),
                connector,
                0.01,
            )
        ) as client,
        client.websocket_connect(
            f"/internal/v1/sessions/{session_id}/cast?pageId=page-a",
            headers={
                "Origin": "https://careeract.example",
                "Cookie": f"{viewer_cookie_name(session_id)}={_token(private_key, session_id)}",
            },
        ) as socket,
    ):
        assert socket.receive_text() == "from-steel"
        with pytest.raises(WebSocketDisconnect) as disconnected:
            socket.receive_text()
        assert disconnected.value.code == 1011
    assert store.drained and not store.released


def test_viewer_cast_closes_when_coordination_becomes_unavailable() -> None:
    class UnavailableStore(_ViewerStore):
        async def renew_viewer(self, command: BrowserCommand, lease_id: UUID) -> None:
            if self.calls >= 2:
                raise PoolTimeoutError("coordination unavailable")
            await super().renew_viewer(command, lease_id)

    session_id = uuid4()
    private_key = Ed25519PrivateKey.generate()
    store = UnavailableStore()
    with (
        TestClient(
            _app(
                private_key,
                store,
                _steel_client(lambda _: httpx.Response(500), session_id),
                _Connector(_Upstream()),
                0.01,
            )
        ) as client,
        client.websocket_connect(
            f"/internal/v1/sessions/{session_id}/cast?pageId=page-a",
            headers={
                "Origin": "https://careeract.example",
                "Cookie": f"{viewer_cookie_name(session_id)}={_token(private_key, session_id)}",
            },
        ) as socket,
    ):
        assert socket.receive_text() == "from-steel"
        with pytest.raises(WebSocketDisconnect) as disconnected:
            socket.receive_text()
        assert disconnected.value.code == 1013


def test_viewer_cast_rechecks_authorization_after_upstream_connect_before_accept() -> None:
    session_id = uuid4()
    private_key = Ed25519PrivateKey.generate()
    store = _ViewerStore(reject_after=1)
    with (
        TestClient(
            _app(
                private_key,
                store,
                _steel_client(lambda _: httpx.Response(500), session_id),
                _Connector(_Upstream()),
            )
        ) as client,
        pytest.raises(WebSocketDisconnect) as disconnected,
        client.websocket_connect(
            f"/internal/v1/sessions/{session_id}/cast?pageId=page-a",
            headers={
                "Origin": "https://careeract.example",
                "Cookie": f"{viewer_cookie_name(session_id)}={_token(private_key, session_id)}",
            },
        ),
    ):
        pass
    assert disconnected.value.code == 1008
    assert store.drained and store.released
