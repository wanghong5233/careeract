import json
import os
from uuid import uuid4

import httpx
import pytest
from playwright.async_api import Error as PlaywrightError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.browser.sessions.steel import (
    SteelSessionConflict,
    SteelSessionManager,
    SteelSessionUnavailable,
    SteelSessionUncertain,
)
from tests.browser.test_browser_context import scope, synthetic_context
from tests.browser.test_postgres_leases import database_url as database_url
from tests.browser.test_steel_sessions import SyntheticSteel
from tests.browser.test_steel_sessions import engine as engine

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL integration",
)


def synthetic_snapshot() -> dict[str, object]:
    return {
        "cookies": synthetic_context().to_steel()["cookies"],
        "origins": [
            {
                "origin": "https://example.com",
                "localStorage": [{"name": "synthetic", "value": "synthetic-private-state"}],
            }
        ],
    }


class SyntheticReader:
    def __init__(self, steel: SyntheticSteel, failure: str | None = None) -> None:
        self.steel = steel
        self.failure = failure
        self.observed = 0

    async def storage_state(self) -> object:
        self.observed += 1
        if self.failure == "replace":
            self.steel.sessions = [{"id": str(uuid4()), "status": "live"}]
        if self.failure == "empty":
            return {"cookies": [], "origins": []}
        if self.failure == "invalid":
            return {"cookies": "private diagnostic"}
        if self.failure == "legacy":
            return synthetic_context().to_steel()
        if self.failure == "oversize":
            return {
                "cookies": [],
                "origins": [
                    {
                        "origin": "https://example.com",
                        "localStorage": [{"name": "private", "value": "x" * (1024 * 1024)}],
                    }
                ],
            }
        if self.failure == "timeout":
            raise TimeoutError("private diagnostic")
        if self.failure == "disconnected":
            raise PlaywrightError("private diagnostic")
        return synthetic_snapshot()


@pytest.mark.asyncio
async def test_export_requires_owned_live_session_and_rechecks_inventory(
    engine: AsyncEngine,
) -> None:
    steel = SyntheticSteel()
    reader = SyntheticReader(steel)
    session_id = uuid4()

    def respond(request: httpx.Request) -> httpx.Response:
        assert not request.url.path.endswith("/context")
        return steel.respond(request)

    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(respond)
    ) as client:
        manager = SteelSessionManager(client, engine)
        with pytest.raises(SteelSessionConflict):
            await manager.export_context(session_id, scope(), browser_context=reader)
        assert not reader.observed
        await manager.create(session_id)
        assert (
            await manager.export_context(session_id, scope(), browser_context=reader)
            == synthetic_context()
        )
        reader.failure = "replace"
        with pytest.raises(SteelSessionUncertain):
            await manager.export_context(session_id, scope(), browser_context=reader)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["empty", "invalid", "legacy", "oversize", "timeout", "disconnected"]
)
async def test_export_failure_does_not_return_empty_state_or_retry(
    engine: AsyncEngine, failure: str
) -> None:
    steel = SyntheticSteel()
    reader = SyntheticReader(steel, failure)
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as client:
        manager = SteelSessionManager(client, engine)
        session_id = uuid4()
        await manager.create(session_id)
        with pytest.raises(SteelSessionUnavailable) as failed:
            await manager.export_context(session_id, scope(), browser_context=reader)
        assert reader.observed == 1
        assert "private" not in str(failed.value)


@pytest.mark.asyncio
async def test_context_is_imported_only_once_through_reserved_creation(engine: AsyncEngine) -> None:
    steel = SyntheticSteel()
    imported: list[object] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/sessions":
            imported.append(json.loads(request.content)["sessionContext"])
        return steel.respond(request)

    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(respond)
    ) as client:
        manager = SteelSessionManager(client, engine)
        session_id = uuid4()
        await manager.create(session_id, context=synthetic_context())
        assert imported == [synthetic_context().to_steel()]
        with pytest.raises(SteelSessionConflict):
            await manager.create(session_id, context=synthetic_context())
        assert len(imported) == 1
