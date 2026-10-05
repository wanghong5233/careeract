import asyncio
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from ag_ui.core import EventType, RunAgentInput, RunFinishedEvent, RunStartedEvent
from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.message import Message
from agno.run.agent import RunOutput
from agno.run.base import RunStatus
from agno.session.agent import AgentSession
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Request
from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.app.factory import create_app
from services.api.infrastructure.agent_execution import lock_runtime, unlock_runtime
from services.api.infrastructure.agent_stream import CareerAGUI
from tests.api.test_agent_sessions import token_for
from tests.api.test_health import build_settings, use_signing_key
from tests.browser.test_postgres_leases import database_url as database_url


@pytest.mark.asyncio
async def test_client_disconnect_drains_framework_stream_before_releasing_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.api.infrastructure.agent_stream as module

    gate, released = asyncio.Event(), asyncio.Event()

    @asynccontextmanager
    async def accept(*_: object) -> AsyncIterator[None]:
        try:
            yield
        finally:
            released.set()

    async def events(*_: object, **__: object) -> AsyncIterator[Any]:
        yield RunStartedEvent(type=EventType.RUN_STARTED, thread_id="synthetic", run_id="run")
        await gate.wait()
        yield RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="synthetic", run_id="run")

    monkeypatch.setattr(module, "run_entity", events)
    agent = AsyncMock()
    agent.aget_run_output.return_value = SimpleNamespace(status="COMPLETED")
    adapter = CareerAGUI(agent)
    endpoint = next(
        cast(Any, route).endpoint
        for route in adapter.get_router().routes
        if getattr(route, "path", None) == "/agui"
    )
    app = FastAPI()
    app.state.agent_execution = SimpleNamespace(accept=accept)
    request = Request({"type": "http", "app": app, "state": {"user_id": "synthetic-owner"}})
    response = await endpoint(
        request,
        RunAgentInput(
            thread_id="synthetic",
            run_id="run",
            messages=[],
            tools=[],
            context=[],
            forwarded_props={},
        ),
    )
    iterator = response.body_iterator
    assert "RUN_STARTED" in await anext(iterator)
    await iterator.aclose()
    assert not released.is_set()
    gate.set()
    await asyncio.wait_for(released.wait(), 5)
    await asyncio.sleep(0)
    assert not adapter._streams


@pytest.mark.skipif(
    os.environ.get("RUN_PROJECT_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL reconciliation",
)
@pytest.mark.asyncio
async def test_reconciliation_refuses_live_or_other_owned_runs_and_preserves_unknown_history(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    settings = build_settings().model_copy(update={"database_url": PostgresDsn(database_url)})
    db = PostgresDb(db_url=database_url.replace("+asyncpg", "+psycopg"), db_schema="reconcile_test")
    agent = Agent(id="careeract-agent", db=db, telemetry=False)

    class Runtime:
        agents = [agent]

        def get_app(self) -> FastAPI:
            return FastAPI()

    app = create_app(settings, lambda _: Runtime())
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            for identifier in ("reconcile-owner", "reconcile-other"):
                await connection.execute(
                    text(
                        'INSERT INTO auth."user" (id,name,email,"emailVerified") '
                        "VALUES (:id,:id,:email,false)"
                    ),
                    {"id": identifier, "email": identifier + "@example.invalid"},
                )
        owner = {"Authorization": "Bearer " + token_for(private_key, "reconcile-owner")}
        other = {"Authorization": "Bearer " + token_for(private_key, "reconcile-other")}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            conversation = (
                await client.post(
                    "/api/v1/agent/conversations", headers=owner, json={"id": str(uuid4())}
                )
            ).json()
            session_id = conversation["session_id"]
            run = RunOutput(
                agent_id="careeract-agent",
                run_id="synthetic-orphan",
                session_id=session_id,
                user_id="reconcile-owner",
                status=RunStatus.running,
                messages=[
                    Message(id="synthetic-input", role="user", content="合成中断任务"),
                    Message(id="synthetic-partial", role="assistant", content="合成保存片段"),
                ],
            )
            await asyncio.to_thread(
                db.upsert_session,
                AgentSession(
                    session_id=session_id,
                    user_id="reconcile-owner",
                    runs=[run],
                    created_at=int(time.time()),
                ),
            )
            await asyncio.to_thread(
                db.upsert_run, run, session_id=session_id, user_id="reconcile-owner"
            )
            path = f"/api/v1/agent/conversations/{session_id}/reconcile"
            assert (
                await client.post(path, headers=other, json={"run_id": run.run_id})
            ).status_code == 404
            async with engine.connect() as connection:
                await lock_runtime(connection, "careeract_conversation", session_id)
                assert (
                    await client.post(path, headers=owner, json={"run_id": run.run_id})
                ).status_code == 409
                await unlock_runtime(connection, "careeract_conversation", session_id)
            assert (
                await client.post(path, headers=owner, json={"run_id": "missing"})
            ).status_code == 404
            response = await client.post(path, headers=owner, json={"run_id": run.run_id})
            assert response.status_code == 200 and response.json()["status"] == "INTERRUPTED"
            assert (await client.post(path, headers=owner, json={"run_id": run.run_id})).json()[
                "status"
            ] == "INTERRUPTED"
            history = (
                await client.get(
                    "/api/v1/agent/session/history",
                    headers=owner,
                    params={"session_id": session_id},
                )
            ).json()
            assert [item["content"] for item in history["messages"]] == [
                "合成中断任务",
                "合成保存片段",
            ]
            assert all(item["run_status"] == "INTERRUPTED" for item in history["messages"])
            assert not await app.state.agent_history_reader.has_active_run(
                session_id=session_id, user_id="reconcile-owner"
            )
            async with app.state.agent_execution.accept(
                SimpleNamespace(user_id="reconcile-owner"), session_id, "synthetic-next"
            ):
                pass
    finally:
        await engine.dispose()
        db.db_engine.dispose()
