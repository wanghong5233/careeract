from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.application.ports.browser_control import (
    BrowserControlConflict,
    BrowserControlRejected,
)
from services.api.infrastructure.browser_control import BrowserCommandSigner, BrowserControlClient
from services.browser.app.factory import create_app
from services.browser.sessions.authentication import CommandVerifier
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.sessions.profiles import PostgresBrowserProfileStore, ProfileCipher
from services.browser.sessions.steel import SteelSessionManager
from services.browser.site_adapters.boss_context import BOSS_SCOPE, BossContextReader
from tests.api.test_browser_control import control_context
from tests.browser.test_browser_profiles import add_user
from tests.browser.test_signed_lifecycle import database_url as database_url
from tests.browser.test_signed_lifecycle import engine as engine
from tests.browser.test_signed_lifecycle import pytestmark as pytestmark
from tests.browser.test_steel_sessions import SyntheticSteel


@pytest.mark.parametrize("authenticated", [True, False])
async def test_finish_saves_only_verified_state_and_releases_with_evidence(
    engine: AsyncEngine, authenticated: bool
) -> None:
    steel = SyntheticSteel()
    key = Ed25519PrivateKey.generate()
    context = replace(control_context(), owner_id="boss-login", user_id=await add_user(engine))
    profiles = PostgresBrowserProfileStore(engine, ProfileCipher(b"f" * 32), BOSS_SCOPE)
    reader = AsyncMock(
        return_value={
            "authenticated": authenticated,
            "cookies": [
                {
                    "name": "synthetic",
                    "value": "value",
                    "domain": ".zhipin.com",
                    "path": "/",
                    "expires": -1,
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax",
                }
            ],
            "origins": [
                {
                    "origin": "https://www.zhipin.com",
                    "localStorage": [{"name": "synthetic", "value": "value"}],
                }
            ],
        }
    )
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as steel_client:
        store = PostgresLeaseStore(engine)
        app = create_app(
            verifier=CommandVerifier(key.public_key()),
            store=store,
            steel_sessions=SteelSessionManager(steel_client, engine),
            profiles=profiles,
            context_reader=lambda _session: cast(
                BossContextReader, SimpleNamespace(storage_state=reader)
            ),
        )
        async with httpx.AsyncClient(
            base_url="http://browser", transport=httpx.ASGITransport(app=app)
        ) as client:
            adapter = BrowserControlClient(client, BrowserCommandSigner(key))
            await adapter.send(context, "register")
            await adapter.lifecycle(context, "create")
            with pytest.raises(BrowserControlRejected):
                await adapter.lifecycle(context, "finish")
            lease = await adapter.send(context, "acquire")
            assert lease is not None
            await adapter.send(context, "revoke")
            with pytest.raises(BrowserControlConflict):
                await adapter.lifecycle(context, "finish")
            reader.assert_not_awaited()
            await store.confirm_stopped(context.session_id, lease.lease_id)
            result = await adapter.lifecycle(context, "finish")
            assert result.status == "released" and result.login_verified is authenticated
            assert bool(await profiles.current(context.user_id)) is authenticated
            assert len(steel.writes) == 2
            reader.assert_awaited_once()
            with pytest.raises(BrowserControlConflict):
                await adapter.lifecycle(context, "finish")
            with pytest.raises(BrowserControlRejected):
                await adapter.lifecycle(replace(context, user_id="other"), "finish")
