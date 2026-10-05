import asyncio
import json
import os
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.message import Message
from agno.run.agent import RunOutput
from agno.run.base import RunContext, RunStatus
from agno.session.agent import AgentSession
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.app.factory import create_app
from services.api.application.context import ActorContext
from services.api.domain.work_session import WorkSessionHistoryUnavailable
from services.api.infrastructure.agent_execution import lock_runtime, unlock_runtime
from services.api.infrastructure.side_chats import AgnoSideChatRuntime
from tests.api.test_agent_sessions import token_for
from tests.api.test_health import build_settings, use_signing_key
from tests.browser.test_postgres_leases import database_url as database_url


def synthetic_run(identifier: str, scope: str, content: str) -> RunOutput:
    return RunOutput(
        run_id=identifier,
        agent_id="careeract-agent",
        user_id="side-owner",
        status=RunStatus.completed,
        metadata={"career_scope": scope},
        messages=[
            Message(id=identifier + "-input", role="user", content="合成问题"),
            Message(id=identifier + "-reply", role="assistant", content=content),
            Message(id=identifier + "-tool", role="tool", content="不得带入工具轨迹"),
        ],
    )


@pytest.mark.asyncio
async def test_side_history_fixed_cutoff_scope_and_failure_are_not_empty_success() -> None:
    scope = str(uuid4())
    source = SimpleNamespace(session_id="conversation:synthetic", context_version=scope)
    sessions = SimpleNamespace(read=AsyncMock(return_value=source))
    first = synthetic_run("first", scope, "合成原回答")
    wrong = synthetic_run("wrong", str(uuid4()), "另一项目")
    later = synthetic_run("later", scope, "合成新增回答")
    agent = SimpleNamespace(
        aget_session=AsyncMock(
            return_value=AgentSession(
                session_id="conversation:synthetic", runs=[first, wrong, later]
            )
        )
    )
    runtime = AgnoSideChatRuntime(Any, sessions, agent)  # type: ignore[arg-type]
    context = RunContext(
        run_id="side-run",
        session_id="side:synthetic",
        user_id="side-owner",
        metadata={
            "career_side": {
                "source_id": "conversation:synthetic",
                "source_scope": scope,
                "eligible_runs": [first.run_id],
            }
        },
    )
    read = runtime.history_tool(context)
    result = json.loads(await read())
    assert [item["content"] for item in result["messages"]] == ["合成问题", "合成原回答"]
    assert result["reference_only"] is True
    context.metadata["career_side"]["eligible_runs"].append(later.run_id)
    assert len(json.loads(await read())["messages"]) == 4
    source.context_version = str(uuid4())
    assert json.loads(await read())["messages"] == []
    sessions.read.side_effect = WorkSessionHistoryUnavailable("synthetic unavailable")
    assert json.loads(await read())["status"] == "unavailable"
    assert json.loads(await read(start=-1))["status"] == "unavailable"


@pytest.mark.skipif(
    os.environ.get("RUN_PROJECT_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL side chat",
)
@pytest.mark.asyncio
async def test_temporary_chat_ownership_scope_lifecycle_and_framework_history(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, key)
    settings = build_settings().model_copy(update={"database_url": PostgresDsn(database_url)})
    db = PostgresDb(db_url=database_url.replace("+asyncpg", "+psycopg"), db_schema="side_test")
    agent = Agent(id="careeract-agent", db=db, telemetry=False)

    class Runtime:
        agents = [agent]

        def get_app(self) -> FastAPI:
            return FastAPI()

    app = create_app(settings, lambda _: Runtime())
    engine = create_async_engine(database_url)
    owner = {"Authorization": "Bearer " + token_for(key, "side-owner")}
    other = {"Authorization": "Bearer " + token_for(key, "side-other")}
    try:
        async with engine.begin() as connection:
            for identifier in ("side-owner", "side-other"):
                await connection.execute(
                    text(
                        'INSERT INTO auth."user" (id,name,email,"emailVerified") '
                        "VALUES (:id,:id,:email,false)"
                    ),
                    {"id": identifier, "email": identifier + "@example.invalid"},
                )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            main = (
                await client.post(
                    "/api/v1/agent/conversations", headers=owner, json={"id": str(uuid4())}
                )
            ).json()
            actor = ActorContext("side-owner", "synthetic")
            source = await app.state.agent_work_session_service.read(
                actor, session_id=main["session_id"]
            )
            run = synthetic_run("source", str(source.context_version), "合成甲句。合成乙句。")
            await asyncio.to_thread(
                db.upsert_session,
                AgentSession(
                    session_id=source.session_id,
                    user_id=actor.user_id,
                    runs=[run],
                    created_at=int(time.time()),
                ),
            )
            body = {
                "id": str(uuid4()),
                "tab_id": str(uuid4()),
                "source_id": source.session_id,
                "message_id": "source-reply",
                "quote": "合成乙句。",
            }
            await asyncio.to_thread(
                db.upsert_run, run, session_id=source.session_id, user_id=actor.user_id
            )
            assert (
                await client.post("/api/v1/agent/side-chats", headers=other, json=body)
            ).status_code == 404
            assert (
                await client.post(
                    "/api/v1/agent/side-chats", headers=owner, json={**body, "quote": "伪造引用"}
                )
            ).status_code == 409
            created = await client.post("/api/v1/agent/side-chats", headers=owner, json=body)
            assert created.status_code == 201, created.text
            side = created.json()
            assert side["side_context"]["quote"] == "合成乙句。"
            assert (await client.post("/api/v1/agent/side-chats", headers=owner, json=body)).json()[
                "session_id"
            ] == side["session_id"]
            assert (
                await client.post(
                    "/api/v1/agent/side-chats", headers=owner, json={**body, "id": str(uuid4())}
                )
            ).status_code == 409
            assert (
                len(
                    (await client.get("/api/v1/agent/conversations", headers=owner)).json()["items"]
                )
                == 1
            )
            assert (
                await client.get(
                    "/api/v1/agent/session/history",
                    headers=other,
                    params={"session_id": side["session_id"]},
                )
            ).status_code == 404
            assert (
                await client.patch(
                    f"/api/v1/agent/conversations/{side['session_id']}",
                    headers=owner,
                    json={"version": side["version"], "project_id": None},
                )
            ).status_code == 422
            side_record = await app.state.agent_work_session_service.read(
                actor, session_id=side["session_id"]
            )
            context = RunContext(
                run_id="side-run", session_id=side_record.session_id, user_id=actor.user_id
            )
            await app.state.side_chat_service.runtime.scope_hook()(
                context, AgentSession(session_id=side_record.session_id)
            )
            assert context.metadata["career_side"]["eligible_runs"] == [run.run_id]
            assert len(context.metadata["career_side"]["nearby"]) == 2
            project = (
                await client.post(
                    "/api/v1/projects", headers=owner, json={"title": "合成范围隔离项目"}
                )
            ).json()
            scoped_main = (
                await client.patch(
                    f"/api/v1/agent/conversations/{source.session_id}",
                    headers=owner,
                    json={"version": main["version"], "project_id": project["id"]},
                )
            ).json()
            assert scoped_main["project_id"] == project["id"]
            assert (
                json.loads(await app.state.side_chat_service.runtime.history_tool(context)())[
                    "messages"
                ]
                == []
            )
            assert (
                await app.state.agent_work_session_service.read(
                    actor, session_id=side["session_id"]
                )
            ).project_id is None
            project_side = (
                await client.post(
                    "/api/v1/agent/side-chats",
                    headers=owner,
                    json={
                        "id": str(uuid4()),
                        "tab_id": str(uuid4()),
                        "source_id": source.session_id,
                    },
                )
            ).json()
            assert project_side["project_id"] == project["id"]
            deleted = await client.request(
                "DELETE",
                f"/api/v1/projects/{project['id']}",
                headers=owner,
                json={"version": project["version"]},
            )
            assert deleted.status_code == 204
            assert (
                await app.state.agent_work_session_service.read(
                    actor, session_id=project_side["session_id"]
                )
            ).project_id is None
            assert (
                await client.post(
                    f"/api/v1/agent/side-chats/{project_side['session_id']}/close",
                    headers=owner,
                    json={},
                )
            ).status_code == 200
            path = f"/api/v1/agent/side-chats/{side['session_id']}/close"
            async with engine.connect() as connection:
                await lock_runtime(connection, "careeract_conversation", side["session_id"])
                assert (await client.post(path, headers=owner, json={})).status_code == 409
                await unlock_runtime(connection, "careeract_conversation", side["session_id"])
            assert (await client.post(path, headers=owner, json={})).status_code == 200
            assert (
                await client.get(f"/api/v1/agent/conversations/{side['session_id']}", headers=owner)
            ).status_code == 404
            assert (await agent.aget_session(source.session_id, user_id=actor.user_id)) is not None
            expired_body = {**body, "id": str(uuid4()), "message_id": None, "quote": ""}
            expired = (
                await client.post("/api/v1/agent/side-chats", headers=owner, json=expired_body)
            ).json()
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE career.agent_work_sessions SET "
                        "temporary_until=clock_timestamp()-interval '1 hour' WHERE session_id=:id"
                    ),
                    {"id": expired["session_id"]},
                )
            assert (
                await client.get(
                    f"/api/v1/agent/conversations/{expired['session_id']}", headers=owner
                )
            ).status_code == 404
            await app.state.side_chat_service.runtime.cleanup()
            assert (
                await app.state.agent_work_session_service.repository.get(
                    actor, expired["session_id"]
                )
                is None
            )
    finally:
        await engine.dispose()
        db.db_engine.dispose()
