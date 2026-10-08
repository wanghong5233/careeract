from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from services.api.app.factory import create_app
from services.api.application.boss_login import BossLoginService
from services.api.application.browser_registration import BrowserRegistrationService
from services.api.infrastructure.boss_connections import PostgresBossConnectionRepository
from services.api.infrastructure.browser_control import BrowserCommandSigner, BrowserControlClient
from services.api.infrastructure.execution import PostgresExecutionRepository
from services.browser.app.factory import create_app as create_browser_app
from services.browser.sessions.authentication import CommandVerifier
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.sessions.steel import SteelSessionManager
from tests.api.test_execution_semantics import Scenario
from tests.api.test_execution_semantics import pytestmark as pytestmark
from tests.api.test_execution_semantics import scenario as scenario
from tests.api.test_health import FakeAgentRuntime, build_settings, use_signing_key
from tests.api.test_projects import token_for
from tests.browser.test_postgres_leases import database_url as database_url
from tests.browser.test_steel_sessions import SyntheticSteel


async def test_product_login_requires_explicit_scope_version_and_owned_connection(
    scenario: Scenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, key)
    repository = PostgresExecutionRepository(scenario.engine)
    connections = PostgresBossConnectionRepository(scenario.engine)
    steel = SyntheticSteel()
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as steel_client:
        browser = create_browser_app(
            verifier=CommandVerifier(key.public_key()),
            store=PostgresLeaseStore(scenario.engine),
            steel_sessions=SteelSessionManager(steel_client, scenario.engine),
        )
        async with httpx.AsyncClient(
            base_url="http://browser", transport=httpx.ASGITransport(app=browser)
        ) as browser_client:
            app = create_app(
                build_settings(),
                lambda _settings: FakeAgentRuntime(),
            )
            service = BossLoginService(
                BrowserRegistrationService(
                    repository, BrowserControlClient(browser_client, BrowserCommandSigner(key))
                )
            )
            app.state.boss_login_service = service
            async with httpx.AsyncClient(
                base_url="http://test", transport=httpx.ASGITransport(app=app)
            ) as client:
                path = f"/api/v1/connections/boss/{scenario.connection_id}/login"
                request_key = str(uuid4())
                headers = {
                    "Authorization": "Bearer " + token_for(key, scenario.actor.user_id),
                    "Idempotency-Key": request_key,
                }
                connection = await connections.get_current(scenario.actor)
                assert connection is not None
                payload = {"version": str(connection.version), "authorize_login": True}
                assert (await client.get(path)).status_code == 401
                assert (await client.get(path, headers=headers)).json() is None
                for invalid in (
                    {"version": str(connection.version)},
                    payload | {"authorize_login": False},
                    payload | {"authorize_login": 1},
                    payload | {"authorize_login": "true"},
                    payload | {"user_id": "other"},
                    payload | {"scope": "boss.send"},
                    payload | {"browser_session_id": str(uuid4())},
                ):
                    assert (
                        await client.post(path, headers=headers, json=invalid)
                    ).status_code == 422
                assert not steel.writes
                stale = await client.post(
                    path, headers=headers, json=payload | {"version": str(uuid4())}
                )
                assert stale.status_code == 409
                for method in ("GET", "POST", "DELETE"):
                    other = await client.request(
                        method,
                        path,
                        headers=headers
                        | {"Authorization": "Bearer " + token_for(key, scenario.other.user_id)},
                        json=payload
                        if method == "POST"
                        else {"version": str(connection.version)}
                        if method == "DELETE"
                        else None,
                    )
                    assert other.status_code == 404
                created = await client.post(path, headers=headers, json=payload)
                assert created.status_code == 201
                result = created.json()
                assert result["scope"] == "boss.login"
                assert (
                    result["attempt_status"] == "waiting" and result["outcome"] == "browser_created"
                )
                assert created.headers["cache-control"] == "no-store"
                assert (
                    not {"user_id", "token", "request_key", "websocketUrl", "debugUrl"}
                    & result.keys()
                )
                assert (await client.post(path, headers=headers, json=payload)).json() == result
                assert (await client.get(path, headers=headers)).json() == result
                assert len(steel.writes) == 1
                assert (
                    await client.post(
                        path, headers=headers | {"Idempotency-Key": str(uuid4())}, json=payload
                    )
                ).status_code == 409
                connection = await connections.get_current(scenario.actor)
                assert connection is not None and connection.status == "waiting_for_login"
                stopped = await client.request(
                    "DELETE", path, headers=headers, json={"version": str(connection.version)}
                )
                assert stopped.status_code == 200
                assert stopped.json()["authorization_status"] == "revoked"
                assert stopped.json()["outcome"] == "browser_released"
                assert (
                    await client.request(
                        "DELETE", path, headers=headers, json={"version": str(connection.version)}
                    )
                ).json() == stopped.json()
                assert len(steel.writes) == 2
                assert (await client.post(path, headers=headers, json=payload)).json()[
                    "outcome"
                ] == "browser_released"
                current = await connections.get_current(scenario.actor)
                assert current is not None and current.status == "revoked"


async def test_product_login_unknown_creation_is_readable_without_replaying(
    scenario: Scenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, key)
    steel = SyntheticSteel()
    steel.failure = "timeout"
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as steel_client:
        browser = create_browser_app(
            verifier=CommandVerifier(key.public_key()),
            store=PostgresLeaseStore(scenario.engine),
            steel_sessions=SteelSessionManager(steel_client, scenario.engine),
        )
        async with httpx.AsyncClient(
            base_url="http://browser", transport=httpx.ASGITransport(app=browser)
        ) as browser_client:
            app = create_app(build_settings(), lambda _settings: FakeAgentRuntime())
            app.state.boss_login_service = BossLoginService(
                BrowserRegistrationService(
                    PostgresExecutionRepository(scenario.engine),
                    BrowserControlClient(browser_client, BrowserCommandSigner(key)),
                )
            )
            async with httpx.AsyncClient(
                base_url="http://test", transport=httpx.ASGITransport(app=app)
            ) as client:
                path = f"/api/v1/connections/boss/{scenario.connection_id}/login"
                connection = await PostgresBossConnectionRepository(scenario.engine).get_current(
                    scenario.actor
                )
                assert connection is not None
                headers = {
                    "Authorization": "Bearer " + token_for(key, scenario.actor.user_id),
                    "Idempotency-Key": str(uuid4()),
                }
                payload = {"version": str(connection.version), "authorize_login": True}
                unknown = await client.post(path, headers=headers, json=payload)
                assert unknown.status_code == 503
                assert unknown.json()["error"]["code"] == "execution_unavailable"
                current = (await client.get(path, headers=headers)).json()
                assert (
                    current["attempt_status"] == "unknown"
                    and current["outcome"] == "creation_unconfirmed"
                )
                assert (await client.post(path, headers=headers, json=payload)).json() == current
                assert len(steel.writes) == 1
