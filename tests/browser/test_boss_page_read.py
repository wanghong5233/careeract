from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from services.api.infrastructure.boss_page import BossPageClient
from services.api.infrastructure.browser_control import BrowserCommandSigner
from services.browser.app.factory import create_app
from services.browser.sessions.authentication import (
    BrowserCommand,
    CommandRejected,
    CommandVerifier,
)
from services.browser.sessions.lease import LeaseConflict
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.site_adapters.boss import parse_boss_page
from services.browser.site_adapters.boss_context import (
    BossContextReader,
    BossContextUnavailable,
    BossDisconnectUnconfirmed,
)
from tests.api.test_browser_control import control_context


class SnapshotStore:
    def __init__(self, failure: str | None) -> None:
        self.failure = failure
        self.active = False
        self.entered = False
        self.engine = SimpleNamespace(dispose=AsyncMock())

    @asynccontextmanager
    async def snapshot_guard(self, command: BrowserCommand) -> AsyncIterator[None]:
        self.entered = True
        if self.failure == "revoked":
            raise CommandRejected("unavailable")
        if self.failure == "writer":
            raise LeaseConflict("unavailable")
        self.active = True
        try:
            yield
            if self.failure == "expired":
                raise CommandRejected("expired")
        finally:
            self.active = False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (None, 200),
        ("revoked", 403),
        ("writer", 409),
        ("expired", 403),
        ("capture", 503),
        ("wrong_owner", 403),
        ("watcher", 403),
        ("session", 403),
    ],
)
async def test_signed_page_read_holds_guard_and_rejects_untrusted_results(
    failure: str | None,
    status: int,
) -> None:
    key = Ed25519PrivateKey.generate()
    context = replace(control_context(), owner_id="boss-page-reader")
    store = SnapshotStore(failure)
    page = parse_boss_page(
        html="<main><h1>Unrecognized page</h1></main>",
        url="https://www.zhipin.com/web/geek/chat",
        title="BOSS",
    )

    async def capture() -> object:
        assert store.active
        if failure == "capture":
            raise BossContextUnavailable("private synthetic HTML must not be echoed")
        return page

    read = AsyncMock(side_effect=capture)
    app = create_app(
        verifier=CommandVerifier(key.public_key()),
        store=cast(PostgresLeaseStore, store),
        context_reader=lambda _session: cast(BossContextReader, SimpleNamespace(read_page=read)),
    )
    if failure == "wrong_owner":
        context = replace(context, owner_id="saved-login-viewer")
    token = BrowserCommandSigner(key).sign(
        context, "watcher" if failure == "watcher" else "snapshot"
    )
    session_id = uuid4() if failure == "session" else context.session_id
    async with httpx.AsyncClient(
        base_url="http://browser", transport=httpx.ASGITransport(app=app)
    ) as client:
        response = await client.post(
            f"/internal/v1/sessions/{session_id}/boss/page",
            headers={"Authorization": "Bearer " + token},
        )
        if failure is None:
            observed = await BossPageClient(client, BrowserCommandSigner(key)).read_boss_page(
                context
            )
            assert observed.state == "unknown"
            assert observed.messages == () and observed.conversations == ()
    assert response.status_code == status
    assert "private synthetic" not in response.text
    assert not store.active
    if status == 200:
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json()["session_id"] == str(context.session_id)
        assert response.json()["page"]["state"] == "unknown"
        assert "html" not in response.json()["page"]
        assert read.await_count == 2
    if failure in {"revoked", "writer", "wrong_owner", "watcher", "session"}:
        read.assert_not_awaited()
    if failure in {"wrong_owner", "watcher", "session"}:
        assert not store.entered


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "capture", "disconnect", "writer", "expired"])
async def test_conversation_read_owns_writer_and_only_releases_confirmed_disconnect(
    failure: str | None,
) -> None:
    key = Ed25519PrivateKey.generate()
    context = replace(control_context(), owner_id="boss-page-reader", conversation_id="thread-1")
    lease_id = uuid4()
    calls: list[str] = []

    class Store:
        async def execute(self, command: BrowserCommand) -> object:
            calls.append(command.action)
            if failure == "writer" and command.action == "acquire":
                raise LeaseConflict("Human owns session")
            return SimpleNamespace(lease_id=lease_id)

        @asynccontextmanager
        async def executor_action_guard(self, command: BrowserCommand) -> AsyncIterator[None]:
            assert command.lease_id == lease_id
            calls.append("guard")
            if failure == "expired":
                raise CommandRejected("Expired")
            yield

        async def confirm_stopped(self, session_id: object, lease: object) -> None:
            assert session_id == context.session_id and lease == lease_id
            calls.append("release")

    async def capture(target: str) -> object:
        assert calls[-1] == "guard" and target == "thread-1"
        calls.append("capture")
        if failure == "capture":
            raise BossContextUnavailable("Synthetic private content")
        if failure == "disconnect":
            raise BossDisconnectUnconfirmed("Synthetic private content")
        return parse_boss_page(html="", url="https://www.zhipin.com/web/geek/chat", title="")

    store = Store()
    app = create_app(
        verifier=CommandVerifier(key.public_key()),
        store=cast(PostgresLeaseStore, store),
        context_reader=lambda _: cast(
            BossContextReader, SimpleNamespace(read_conversation=capture)
        ),
    )
    token = BrowserCommandSigner(key).sign(context, "conversation")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://browser"
    ) as client:
        response = await client.post(
            f"/internal/v1/sessions/{context.session_id}/boss/conversation",
            headers={"Authorization": "Bearer " + token},
        )
    assert response.status_code == (
        200
        if failure is None
        else 409
        if failure == "writer"
        else 403
        if failure == "expired"
        else 503
    )
    assert "private" not in response.text
    if failure in {None, "capture"}:
        assert calls[-2:] == ["stop", "release"]
    else:
        assert "release" not in calls
