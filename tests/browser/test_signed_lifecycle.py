import asyncio
import json
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Literal, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from services.api.application.ports.browser_control import (
    BrowserControlConflict,
    BrowserControlRejected,
    BrowserControlUncertain,
)
from services.api.infrastructure.browser_control import BrowserCommandSigner, BrowserControlClient
from services.browser.app.factory import create_app
from services.browser.sessions.authentication import CommandVerifier
from services.browser.sessions.context import BrowserContext
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.sessions.profiles import PostgresBrowserProfileStore
from services.browser.sessions.steel import SteelSessionManager
from services.browser.site_adapters.boss_context import (
    BOSS_SCOPE,
    BossContextReader,
    BossContextUnavailable,
)
from tests.api.test_browser_control import control_context
from tests.browser.test_postgres_leases import database_url as database_url
from tests.browser.test_steel_sessions import SyntheticSteel


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM browser.steel_operations"))
        yield engine
    finally:
        await engine.dispose()


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL integration",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("capture_fails", [False, True])
async def test_saved_profile_restores_and_capture_failure_still_releases(
    engine: AsyncEngine, capture_fails: bool
) -> None:
    steel = SyntheticSteel()
    key = Ed25519PrivateKey.generate()
    context = replace(control_context(), owner_id="boss-login")
    snapshot = BrowserContext.from_steel(
        {"cookies": [{"name": "synthetic", "value": "synthetic", "domain": ".zhipin.com"}]},
        BOSS_SCOPE,
    )
    profiles = AsyncMock()
    profiles.scope = BOSS_SCOPE
    profile = SimpleNamespace(id=uuid4(), version=uuid4())
    profiles.current.return_value = (profile, snapshot)
    created_contexts: list[object] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/sessions":
            created_contexts.append(json.loads(request.content).get("sessionContext"))
        return steel.respond(request)

    reader = AsyncMock()
    reader.storage_state.return_value = {
        "authenticated": True,
        "cookies": snapshot.to_steel()["cookies"],
        "origins": [],
    }
    if capture_fails:
        reader.storage_state.side_effect = BossContextUnavailable("unavailable")
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(respond)
    ) as steel_client:
        app = create_app(
            verifier=CommandVerifier(key.public_key()),
            store=PostgresLeaseStore(engine),
            steel_sessions=SteelSessionManager(steel_client, engine),
            profiles=cast(PostgresBrowserProfileStore, profiles),
            context_reader=lambda _session: cast(BossContextReader, reader),
        )
        async with httpx.AsyncClient(
            base_url="http://browser", transport=httpx.ASGITransport(app=app)
        ) as client:
            adapter = BrowserControlClient(client, BrowserCommandSigner(key))
            await adapter.send(context, "register")
            await adapter.lifecycle(context, "create")
            assert created_contexts == [snapshot.to_steel()]
            profiles.current.assert_awaited_once_with(context.user_id)
            await adapter.send(context, "revoke")
            if capture_fails:
                with pytest.raises(BrowserControlUncertain):
                    await adapter.lifecycle(context, "release")
                profiles.create.assert_not_awaited()
                profiles.save.assert_not_awaited()
            else:
                assert (await adapter.lifecycle(context, "release")).status == "released"
                profiles.save.assert_awaited_once_with(
                    context.user_id, profile.id, snapshot, expected_version=profile.version
                )
            assert any(
                item["id"] == str(context.session_id) and item["status"] == "released"
                for item in steel.sessions
            )


async def test_signed_lifecycle_rejects_wrong_owner_replay_and_active_writer(
    engine: AsyncEngine,
) -> None:
    steel = SyntheticSteel()
    key = Ed25519PrivateKey.generate()
    context = control_context()
    store = PostgresLeaseStore(engine)
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as steel_client:
        app = create_app(
            verifier=CommandVerifier(key.public_key()),
            store=store,
            steel_sessions=SteelSessionManager(steel_client, engine),
        )
        async with httpx.AsyncClient(
            base_url="http://browser", transport=httpx.ASGITransport(app=app)
        ) as client:
            adapter = BrowserControlClient(client, BrowserCommandSigner(key))
            await adapter.send(context, "register")
            for changed in (
                replace(context, user_id="other"),
                replace(context, task_id=uuid4()),
                replace(context, authorization_id=uuid4()),
            ):
                with pytest.raises(BrowserControlRejected):
                    await adapter.lifecycle(changed, "create")
            token = adapter.signer.sign(context, "create")
            path = f"/internal/v1/sessions/{context.session_id}/lifecycle/create"
            assert (await client.post(path)).status_code == 401
            headers = {"Authorization": "Bearer " + token}
            created = await client.post(path, headers=headers)
            assert created.status_code == 200
            assert created.json() == {"session_id": str(context.session_id), "status": "live"}
            assert (await client.post(path, headers=headers)).status_code == 403
            with pytest.raises(BrowserControlConflict):
                await adapter.lifecycle(context, "create")
            with pytest.raises(BrowserControlRejected):
                await adapter.lifecycle(context, "release")
            lease = await adapter.send(context, "acquire")
            assert lease is not None
            await adapter.send(context, "revoke")
            with pytest.raises(BrowserControlConflict):
                await adapter.lifecycle(context, "release")
            assert len(steel.writes) == 1
            await store.confirm_stopped(context.session_id, lease.lease_id)
            expired = replace(
                context, authorization_expires_at=datetime.now(UTC) - timedelta(minutes=1)
            )
            assert (await adapter.lifecycle(expired, "release")).status == "released"
            assert (await adapter.lifecycle(expired, "release")).status == "released"
            assert len(steel.writes) == 2


@pytest.mark.parametrize("operation", ["create", "release"])
async def test_lost_lifecycle_response_cannot_replay_after_restart(
    engine: AsyncEngine, operation: str
) -> None:
    steel = SyntheticSteel()
    key = Ed25519PrivateKey.generate()
    context = control_context()
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as steel_client:
        app = create_app(
            verifier=CommandVerifier(key.public_key()),
            store=PostgresLeaseStore(engine),
            steel_sessions=SteelSessionManager(steel_client, engine),
        )
        async with httpx.AsyncClient(
            base_url="http://browser", transport=httpx.ASGITransport(app=app)
        ) as client:
            adapter = BrowserControlClient(client, BrowserCommandSigner(key))
            await adapter.send(context, "register")
            if operation == "release":
                await adapter.lifecycle(context, "create")
                await adapter.send(context, "revoke")
            steel.failure = "timeout"
            action: Literal["create", "release"] = "create" if operation == "create" else "release"
            with pytest.raises(BrowserControlUncertain):
                await adapter.lifecycle(context, action)
            await engine.dispose()
            rebuilt = create_app(
                verifier=CommandVerifier(key.public_key()),
                store=PostgresLeaseStore(engine),
                steel_sessions=SteelSessionManager(steel_client, engine),
            )
            async with httpx.AsyncClient(
                base_url="http://browser", transport=httpx.ASGITransport(app=rebuilt)
            ) as next_client:
                next_adapter = BrowserControlClient(next_client, BrowserCommandSigner(key))
                with pytest.raises(BrowserControlConflict):
                    await next_adapter.lifecycle(context, action)
            assert len(steel.writes) == (1 if action == "create" else 2)


async def test_creation_holds_session_fence_until_readback(engine: AsyncEngine) -> None:
    steel = SyntheticSteel()
    key = Ed25519PrivateKey.generate()
    context = control_context()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            entered.set()
            await finish.wait()
        return steel.respond(request)

    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(respond)
    ) as steel_client:
        store = PostgresLeaseStore(engine)
        app = create_app(
            verifier=CommandVerifier(key.public_key()),
            store=store,
            steel_sessions=SteelSessionManager(steel_client, engine),
        )
        async with httpx.AsyncClient(
            base_url="http://browser", transport=httpx.ASGITransport(app=app)
        ) as client:
            adapter = BrowserControlClient(client, BrowserCommandSigner(key))
            await adapter.send(context, "register")
            creating = asyncio.create_task(adapter.lifecycle(context, "create"))
            await asyncio.wait_for(entered.wait(), 5)
            acquiring = asyncio.create_task(adapter.send(context, "acquire"))
            await asyncio.sleep(0.05)
            assert not acquiring.done()
            finish.set()
            assert (await creating).status == "live"
            lease = await acquiring
            assert lease is not None
            await adapter.send(context, "revoke")
            await store.confirm_stopped(context.session_id, lease.lease_id)
            await adapter.lifecycle(context, "release")


@pytest.mark.skipif(
    os.environ.get("RUN_STEEL_SESSION_TEST") != "1", reason="Opt-in real local Steel lifecycle"
)
async def test_signed_route_creates_and_releases_real_steel(engine: AsyncEngine) -> None:
    key = Ed25519PrivateKey.generate()
    context = control_context()
    async with httpx.AsyncClient(base_url="http://127.0.0.1:3001") as steel_client:
        app = create_app(
            verifier=CommandVerifier(key.public_key()),
            store=PostgresLeaseStore(engine),
            steel_sessions=SteelSessionManager(steel_client, engine),
        )
        async with httpx.AsyncClient(
            base_url="http://browser", transport=httpx.ASGITransport(app=app)
        ) as client:
            adapter = BrowserControlClient(client, BrowserCommandSigner(key))
            await adapter.send(context, "register")
            created = await adapter.lifecycle(context, "create")
            try:
                assert created.session_id == context.session_id and created.status == "live"
            finally:
                await adapter.send(context, "revoke")
                assert (await adapter.lifecycle(context, "release")).status == "released"
