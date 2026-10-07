import asyncio
import json
import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from services.browser.sessions.steel import (
    SteelSessionConflict,
    SteelSessionManager,
    SteelSessionUnavailable,
    SteelSessionUncertain,
)
from tests.browser.test_postgres_leases import database_url as database_url

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL integration",
)


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM browser.steel_operations"))
        yield engine
    finally:
        await engine.dispose()


class SyntheticSteel:
    def __init__(self) -> None:
        self.sessions: list[dict[str, str]] = [{"id": str(uuid4()), "status": "idle"}]
        self.writes: list[str] = []
        self.failure: str | None = None

    def respond(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"sessions": self.sessions})
        self.writes.append(request.url.path)
        if request.url.path == "/v1/sessions":
            session_id = json.loads(request.content)["sessionId"]
            self.sessions = [{"id": session_id, "status": "live"}]
            result: dict[str, object] = dict(self.sessions[0])
        else:
            self.sessions[0]["status"] = "released"
            result = self.sessions[0].copy() | {"success": True}
            self.sessions.insert(0, {"id": str(uuid4()), "status": "idle"})
        if self.failure == "timeout":
            raise httpx.ReadTimeout("secret diagnostic text", request=request)
        if self.failure == "redirect":
            return httpx.Response(307, headers={"Location": "http://untrusted.invalid"})
        if self.failure == "server":
            return httpx.Response(500, text="secret diagnostic text")
        if self.failure == "invalid":
            return httpx.Response(200, text="secret diagnostic text")
        if self.failure == "wrong-id":
            result["id"] = str(uuid4())
        if self.failure == "wrong-state":
            result["status"] = "idle"
        if self.failure == "false-success":
            result["success"] = False
        if self.failure == "string-success":
            result["success"] = "true"
        if self.failure == "readback":
            self.sessions = [{"id": str(uuid4()), "status": "idle"}]
        result["websocketUrl"] = "ws://secret.invalid"
        return httpx.Response(200, json=result)


@pytest.mark.asyncio
async def test_lifecycle_replay_and_unknown_ids_cannot_release_other_sessions(
    engine: AsyncEngine,
) -> None:
    steel = SyntheticSteel()
    first_id, next_id = uuid4(), uuid4()
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as client:
        manager = SteelSessionManager(client, engine)
        assert await manager.inspect(first_id) is None
        created = await manager.create(first_id)
        assert created.status == "live"
        assert "secret" not in repr(created)
        for conflict_id in (first_id, next_id):
            with pytest.raises(SteelSessionConflict):
                await manager.create(conflict_id)
        with pytest.raises(SteelSessionConflict):
            await manager.release(next_id)
        await manager.release(first_id)
        await manager.create(next_id)
        assert (await manager.release(first_id)).status == "released"
        assert steel.sessions[0]["id"] == str(next_id)
        assert len(steel.writes) == 3
        await manager.release(next_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "release"])
@pytest.mark.parametrize(
    "failure", ["timeout", "redirect", "server", "invalid", "wrong-id", "wrong-state", "readback"]
)
async def test_uncertain_operation_survives_adapter_reconstruction_without_replay(
    engine: AsyncEngine, operation: str, failure: str
) -> None:
    steel = SyntheticSteel()
    session_id = uuid4()
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond), follow_redirects=True
    ) as client:
        manager = SteelSessionManager(client, engine)
        if operation == "release":
            await manager.create(session_id)
        steel.failure = failure
        with pytest.raises(SteelSessionUncertain) as result:
            if operation == "create":
                await manager.create(session_id)
            else:
                await manager.release(session_id)
        assert "secret" not in str(result.value)
        assert len(steel.writes) == (1 if operation == "create" else 2)
        restarted_engine = create_async_engine(str(engine.url))
        try:
            restarted = SteelSessionManager(client, restarted_engine)
            await restarted.inspect(session_id)
            with pytest.raises(SteelSessionConflict):
                await restarted.create(uuid4())
            with pytest.raises(SteelSessionConflict):
                await restarted.release(session_id)
            async with restarted_engine.connect() as connection:
                assert await connection.scalar(
                    text("SELECT state FROM browser.steel_operations WHERE session_id = :id"),
                    {"id": session_id},
                ) == ("creating" if operation == "create" else "releasing")
        finally:
            await restarted_engine.dispose()
        assert len(steel.writes) == (1 if operation == "create" else 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["false-success", "string-success"])
async def test_release_requires_strict_success(engine: AsyncEngine, failure: str) -> None:
    steel = SyntheticSteel()
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as client:
        manager = SteelSessionManager(client, engine)
        session_id = uuid4()
        await manager.create(session_id)
        steel.failure = failure
        with pytest.raises(SteelSessionUncertain):
            await manager.release(session_id)


@pytest.mark.asyncio
async def test_two_process_connections_allow_only_one_creation(engine: AsyncEngine) -> None:
    steel = SyntheticSteel()
    other_engine = create_async_engine(str(engine.url))
    try:
        async with httpx.AsyncClient(
            base_url="http://steel", transport=httpx.MockTransport(steel.respond)
        ) as client:
            results = await asyncio.gather(
                SteelSessionManager(client, engine).create(uuid4()),
                SteelSessionManager(client, other_engine).create(uuid4()),
                return_exceptions=True,
            )
            assert sum(isinstance(result, SteelSessionConflict) for result in results) == 1
            assert len(steel.writes) == 1
    finally:
        await other_engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "release"])
async def test_cancellation_keeps_reservation_and_denies_new_operations(
    engine: AsyncEngine, operation: str
) -> None:
    steel = SyntheticSteel()
    started = asyncio.Event()
    session_id = uuid4()

    async def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            started.set()
            await asyncio.Event().wait()
        return steel.respond(request)

    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as initial_client:
        if operation == "release":
            await SteelSessionManager(initial_client, engine).create(session_id)
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(respond)
    ) as client:
        manager = SteelSessionManager(client, engine)
        pending = asyncio.create_task(
            manager.create(session_id) if operation == "create" else manager.release(session_id)
        )
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            with pytest.raises(SteelSessionConflict):
                await manager.create(uuid4())
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            with pytest.raises(SteelSessionConflict):
                await manager.release(session_id)
        finally:
            if not pending.done():
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await pending


@pytest.mark.asyncio
async def test_changed_upstream_session_blocks_release(engine: AsyncEngine) -> None:
    steel = SyntheticSteel()
    session_id = uuid4()
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as client:
        manager = SteelSessionManager(client, engine)
        await manager.create(session_id)
        steel.sessions = [{"id": str(uuid4()), "status": "live"}]
        with pytest.raises(SteelSessionConflict):
            await manager.release(session_id)
        assert len(steel.writes) == 1
        with pytest.raises(SteelSessionConflict):
            await manager.create(uuid4())


@pytest.mark.asyncio
async def test_unowned_live_session_and_fabricated_detail_are_never_used(
    engine: AsyncEngine,
) -> None:
    steel = SyntheticSteel()
    unowned_id = uuid4()
    steel.sessions = [{"id": str(unowned_id), "status": "live"}]
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as client:
        manager = SteelSessionManager(client, engine)
        assert await manager.inspect(uuid4()) is None
        with pytest.raises(SteelSessionConflict):
            await manager.create(uuid4())
        with pytest.raises(SteelSessionConflict):
            await manager.release(unowned_id)
        assert not steel.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("inventory", ["missing", "duplicate", "multiple-live", "invalid"])
async def test_bad_inventory_cannot_authorize_mutation(engine: AsyncEngine, inventory: str) -> None:
    session_id = str(uuid4())
    rows = [{"id": session_id, "status": "idle"}]
    if inventory == "missing":
        rows = []
    elif inventory == "duplicate":
        rows.append(rows[0].copy())
    elif inventory == "multiple-live":
        rows = [{"id": str(uuid4()), "status": "live"} for _number in range(2)]
    else:
        rows[0]["status"] = "unknown"

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, json={"sessions": rows})

    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(respond)
    ) as client:
        with pytest.raises(SteelSessionUnavailable):
            await SteelSessionManager(client, engine).create(uuid4())


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_STEEL_SESSION_TEST") != "1", reason="Opt-in real local Steel lifecycle"
)
async def test_real_steel_create_inspect_release(engine: AsyncEngine) -> None:
    async with httpx.AsyncClient(base_url="http://127.0.0.1:3001") as client:
        manager = SteelSessionManager(client, engine)
        session_id = uuid4()
        created = await manager.create(session_id)
        try:
            assert created.status == "live"
            assert await manager.inspect(session_id) == created
            with pytest.raises(SteelSessionConflict):
                await manager.create(uuid4())
            with pytest.raises(SteelSessionConflict):
                await manager.release(uuid4())
            assert (await manager.inspect(UUID(str(session_id)))) == created
        finally:
            await manager.release(session_id)
        assert (await manager.inspect(session_id)) is not None
        assert (await manager.release(session_id)).status == "released"
