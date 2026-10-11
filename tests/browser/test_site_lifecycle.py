import json
from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.application.ports.browser_control import BrowserControlRejected
from services.api.infrastructure.browser_control import BrowserCommandSigner, BrowserControlClient
from services.browser.app.factory import create_app
from services.browser.sessions.authentication import CommandVerifier
from services.browser.sessions.context import BrowserContext, SiteScope
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.sessions.profiles import PostgresBrowserProfileStore, ProfileCipher
from services.browser.sessions.site_lifecycle import ProfiledSiteLifecycle, SiteSessionLifecycle
from services.browser.sessions.steel import SteelSessionManager
from tests.api.test_browser_control import control_context
from tests.browser.test_browser_profiles import add_user
from tests.browser.test_signed_lifecycle import database_url as database_url
from tests.browser.test_signed_lifecycle import engine as engine
from tests.browser.test_signed_lifecycle import pytestmark as pytestmark
from tests.browser.test_steel_sessions import SyntheticSteel


@pytest.mark.asyncio
async def test_two_sites_share_signed_lifecycle_without_sharing_profiles(
    engine: AsyncEngine,
) -> None:
    user_id = await add_user(engine)
    other_id = await add_user(engine)
    steel, key = SyntheticSteel(), Ed25519PrivateKey.generate()
    scopes = (
        SiteScope("synthetic-first", ("https://first.example",), ("first.example",)),
        SiteScope("synthetic-second", ("https://second.example",), ("second.example",)),
    )
    bindings: dict[str, SiteSessionLifecycle] = {}
    preparations: dict[str, AsyncMock] = {}
    snapshots: dict[str, BrowserContext] = {}
    stores: dict[str, PostgresBrowserProfileStore] = {}
    for scope in scopes:
        profile_store = PostgresBrowserProfileStore(engine, ProfileCipher(b"s" * 32), scope)
        snapshot = BrowserContext.from_steel(
            {
                "cookies": [
                    {"name": "session", "value": scope.site, "domain": scope.cookie_domains[0]}
                ],
            },
            scope,
        )
        await profile_store.create(user_id, snapshot)
        stores[scope.site], snapshots[scope.site] = profile_store, snapshot
        preparations[scope.site] = AsyncMock()
        bindings[scope.site] = ProfiledSiteLifecycle(
            profile_store,
            prepare=preparations[scope.site],
            capture=AsyncMock(return_value=snapshot),
        )
    supplied: list[object] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/sessions":
            supplied.append(json.loads(request.content).get("sessionContext"))
        return steel.respond(request)

    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(respond)
    ) as client:
        store = PostgresLeaseStore(engine)
        app = create_app(
            verifier=CommandVerifier(key.public_key()),
            store=store,
            steel_sessions=SteelSessionManager(client, engine),
            site_lifecycles=bindings,
        )
        async with httpx.AsyncClient(
            base_url="http://browser", transport=httpx.ASGITransport(app=app)
        ) as browser:
            control = BrowserControlClient(browser, BrowserCommandSigner(key))
            for scope in scopes:
                context = replace(control_context(), owner_id=scope.site, user_id=user_id)
                await control.send(context, "register")
                assert (await control.lifecycle(context, "create")).status == "live"
                preparations[scope.site].assert_awaited_once_with(context.session_id)
                assert supplied[-1] == snapshots[scope.site].to_steel()
                with pytest.raises(BrowserControlRejected):
                    await control.lifecycle(
                        replace(context, owner_id="unconfigured-site"), "create"
                    )
                with pytest.raises(BrowserControlRejected):
                    await control.lifecycle(context, "finish")
                with pytest.raises(BrowserControlRejected):
                    await control.lifecycle(replace(context, user_id=other_id), "release")
                await control.send(context, "revoke")
                assert (await control.lifecycle(context, "release")).status == "released"
                profile = await stores[scope.site].current(user_id)
                assert profile is not None and profile[1] == snapshots[scope.site]
                assert await stores[scope.site].current(other_id) is None
    assert len(supplied) == 2 and supplied[0] != supplied[1]
