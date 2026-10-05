import asyncio
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.metrics import RunMetrics
from agno.models.message import Message
from agno.run.agent import RunOutput
from agno.run.base import RunStatus
from agno.session.agent import AgentSession
from fastapi import FastAPI
from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.app.factory import create_app
from services.api.domain.work_session import WorkSessionHistoryUnavailable
from services.api.infrastructure.agent_sessions import AgnoAgentHistoryReader
from tests.api.test_agent_sessions import token_for
from tests.api.test_health import build_settings, use_signing_key
from tests.browser.test_postgres_leases import database_url as database_url


@pytest.mark.asyncio
async def test_history_includes_cancelled_and_failed_runs_with_their_actual_status() -> None:
    session = AgentSession(
        session_id="synthetic-history",
        user_id="synthetic-owner",
        runs=[
            RunOutput(
                run_id="cancelled-run",
                status=RunStatus.cancelled,
                metrics=RunMetrics(duration=8.4),
                messages=[
                    Message(id="input", role="user", content="合成目标"),
                    Message(id="partial", role="assistant", content="合成部分输出"),
                ],
            ),
            RunOutput(
                run_id="failed-run",
                status=RunStatus.error,
                messages=[Message(id="failed", role="assistant", content="合成失败前输出")],
            ),
        ],
    )
    agent = AsyncMock()
    agent.aget_session.return_value = session
    reader = AgnoAgentHistoryReader(agent)
    messages = await reader.read(
        session_id=session.session_id, user_id="synthetic-owner", limit=100
    )
    assert [(item.id, item.run_status) for item in messages] == [
        ("input", "CANCELLED"),
        ("partial", "CANCELLED"),
        ("failed", "ERROR"),
    ]
    assert messages[1].run_duration_seconds == 8.4
    assert messages[2].run_duration_seconds is None
    assert not await reader.has_active_run(session_id=session.session_id, user_id="synthetic-owner")
    session.runs.append(RunOutput(run_id="running", status=RunStatus.running))
    assert await reader.has_active_run(session_id=session.session_id, user_id="synthetic-owner")


@pytest.mark.asyncio
async def test_history_run_states_accept_database_strings() -> None:
    session = AgentSession(session_id="synthetic-history", user_id="synthetic-owner")
    session.runs = [
        RunOutput(run_id="complete", status=RunStatus.completed),
        RunOutput(run_id="cancel", status=RunStatus.cancelled),
    ]
    for run in session.runs:
        run.status = run.status.value
    agent = AsyncMock()
    agent.aget_session.return_value = session
    reader = AgnoAgentHistoryReader(agent)
    assert await reader.runs(session_id=session.session_id, user_id="synthetic-owner") == [
        {"run_id": "complete", "status": "COMPLETED"},
        {"run_id": "cancel", "status": "CANCELLED"},
    ]
    assert not await reader.has_active_run(session_id=session.session_id, user_id="synthetic-owner")


@pytest.mark.asyncio
async def test_history_failure_does_not_become_empty_history() -> None:
    agent = AsyncMock()
    agent.aget_session.side_effect = ValueError("invalid stored session")
    reader = AgnoAgentHistoryReader(agent)
    with pytest.raises(WorkSessionHistoryUnavailable):
        await reader.read(session_id="synthetic-history", user_id="synthetic-owner", limit=100)
    with pytest.raises(WorkSessionHistoryUnavailable):
        await reader.has_active_run(session_id="synthetic-history", user_id="synthetic-owner")


@pytest.mark.skipif(
    os.environ.get("RUN_PROJECT_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL conversation integration",
)
@pytest.mark.asyncio
async def test_conversation_directory_ownership_versions_history_and_project_deletion(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    settings = build_settings().model_copy(update={"database_url": PostgresDsn(database_url)})
    db = PostgresDb(
        db_url=database_url.replace("+asyncpg", "+psycopg"), db_schema="conversation_test"
    )
    agent = Agent(id="careeract-agent", db=db, telemetry=False)

    class Runtime:
        agents = [agent]

        def get_app(self) -> FastAPI:
            return FastAPI()

    app = create_app(settings, lambda _settings: Runtime())

    class SyntheticHistory:
        active = False
        session_id = ""

        async def read(self, *, session_id: str, user_id: str, limit: int) -> tuple[object, ...]:
            from services.api.application.ports.work_sessions import AgentHistoryMessage

            if session_id == self.session_id:
                return (
                    AgentHistoryMessage(
                        "stored-message",
                        "assistant",
                        "合成已保存片段",
                        1,
                        "stored-cancelled",
                        "CANCELLED",
                    ),
                )
            return ()

        async def basis(self, *, session_id: str, user_id: str) -> object:
            from services.api.application.ports.work_sessions import AgentContextBasis

            return AgentContextBasis(None)

        async def has_active_run(self, *, session_id: str, user_id: str) -> bool:
            return session_id == self.session_id and self.active

    synthetic_history = SyntheticHistory()
    app.state.agent_history_reader = synthetic_history
    app.state.agent_work_session_service.history = synthetic_history
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            for user_id in ("conversation-first", "conversation-second"):
                await connection.execute(
                    text(
                        'INSERT INTO auth."user" (id, name, email, "emailVerified") '
                        "VALUES (:id, 'Synthetic', :email, false)"
                    ),
                    {"id": user_id, "email": user_id + "@example.invalid"},
                )
        first = {"Authorization": "Bearer " + token_for(private_key, "conversation-first")}
        second = {"Authorization": "Bearer " + token_for(private_key, "conversation-second")}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            project = (
                await client.post("/api/v1/projects", headers=first, json={"title": "合成项目"})
            ).json()
            identifier = str(uuid4())
            payload = {"id": identifier, "title": "合成对话一", "project_id": project["id"]}
            created = await client.post("/api/v1/agent/conversations", headers=first, json=payload)
            assert created.status_code == 201
            conversation = created.json()
            session_id = conversation["session_id"]
            synthetic_history.session_id = session_id
            replay = await client.post("/api/v1/agent/conversations", headers=first, json=payload)
            assert replay.json()["version"] == conversation["version"]
            assert (
                await client.post("/api/v1/agent/conversations", headers=second, json=payload)
            ).status_code == 404
            assert (
                await client.get(f"/api/v1/agent/conversations/{session_id}", headers=second)
            ).status_code == 404
            assert (
                await client.patch(
                    f"/api/v1/agent/conversations/{session_id}",
                    headers=second,
                    json={"version": conversation["version"], "title": "越权修改"},
                )
            ).status_code == 404
            assert (
                await client.get(
                    "/api/v1/agent/session/history",
                    headers=second,
                    params={"session_id": session_id},
                )
            ).status_code == 404
            assert (
                await client.post(
                    "/api/v1/agent/conversations",
                    headers=first,
                    json={**payload, "session_id": "forged"},
                )
            ).status_code == 422
            other = (
                await client.post(
                    "/api/v1/agent/conversations",
                    headers=first,
                    json={"id": str(uuid4()), "title": "合成对话二", "project_id": project["id"]},
                )
            ).json()
            empty = await client.get(
                "/api/v1/agent/session/history",
                headers=first,
                params={"session_id": other["session_id"]},
            )
            assert empty.status_code == 200 and empty.json()["messages"] == []
            history = await client.get(
                "/api/v1/agent/session/history", headers=first, params={"session_id": session_id}
            )
            assert history.json()["messages"][0]["run_status"] == "CANCELLED"
            assert history.json()["messages"][0]["run_id"] == "stored-cancelled"
            assert history.headers["cache-control"] == "no-store"
            changes = {"version": conversation["version"], "title": "合成更名"}
            responses = await asyncio.gather(
                *[
                    client.patch(
                        f"/api/v1/agent/conversations/{session_id}", headers=first, json=changes
                    )
                    for _ in range(2)
                ]
            )
            assert sorted(response.status_code for response in responses) == [200, 409]
            latest = next(response.json() for response in responses if response.status_code == 200)
            synthetic_history.active = True
            blocked = await client.patch(
                f"/api/v1/agent/conversations/{session_id}",
                headers=first,
                json={"version": latest["version"], "project_id": None},
            )
            assert blocked.status_code == 409
            synthetic_history.active = False
            archived = await client.patch(
                f"/api/v1/agent/conversations/{session_id}",
                headers=first,
                json={"version": latest["version"], "archived": True},
            )
            assert archived.status_code == 200
            assert (
                len(
                    (
                        await client.get(
                            "/api/v1/agent/conversations",
                            headers=first,
                            params={"archived": "true"},
                        )
                    ).json()["items"]
                )
                == 1
            )
            restored = await client.patch(
                f"/api/v1/agent/conversations/{session_id}",
                headers=first,
                json={"version": archived.json()["version"], "archived": False},
            )
            assert restored.status_code == 200
            page = (
                await client.get("/api/v1/agent/conversations", headers=first, params={"limit": 1})
            ).json()
            next_page = (
                await client.get(
                    "/api/v1/agent/conversations",
                    headers=first,
                    params={"limit": 1, "cursor": page["next_cursor"]},
                )
            ).json()
            assert {page["items"][0]["session_id"], next_page["items"][0]["session_id"]} == {
                session_id,
                other["session_id"],
            }
            assert (
                await client.get(
                    "/api/v1/agent/conversations", headers=first, params={"cursor": "bad"}
                )
            ).status_code == 422
            legacy = await client.put(
                "/api/v1/agent/session", headers=first, json={"session_id": "synthetic-legacy"}
            )
            assert legacy.status_code == 200
            directory = (await client.get("/api/v1/agent/conversations", headers=first)).json()
            assert any(
                item["session_id"] == "synthetic-legacy" and item["title"] == "历史对话"
                for item in directory["items"]
            )
            assert (
                await client.put(
                    "/api/v1/agent/session", headers=first, json={"session_id": session_id}
                )
            ).status_code == 422
            deleted = await client.request(
                "DELETE",
                f"/api/v1/projects/{project['id']}",
                headers=first,
                json={"version": project["version"]},
            )
            assert deleted.status_code == 204
            detached = (
                await client.get(f"/api/v1/agent/conversations/{session_id}", headers=first)
            ).json()
            assert (
                detached["project_id"] is None and detached["version"] != restored.json()["version"]
            )
            assert (
                await client.patch(
                    f"/api/v1/agent/conversations/{session_id}",
                    headers=first,
                    json={"version": restored.json()["version"], "title": "过期写入"},
                )
            ).status_code == 409
            assert (
                await client.get(
                    "/api/v1/agent/session/history",
                    headers=first,
                    params={"session_id": session_id},
                )
            ).json()["messages"][0]["content"] == "合成已保存片段"
            assert (await client.get("/api/v1/agent/conversations", headers=second)).json()[
                "items"
            ] == []
    finally:
        await engine.dispose()
        db.db_engine.dispose()
