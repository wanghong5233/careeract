import asyncio
import os
import time
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.message import Message
from agno.run.agent import RunOutput
from agno.run.base import RunStatus
from agno.session.agent import AgentSession
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.app.factory import create_app
from services.api.domain.work_session import WorkSessionConflict, WorkSessionHistoryUnavailable
from services.api.infrastructure.agent_execution import lock_runtime, unlock_runtime
from services.api.infrastructure.conversation_branches import (
    AgnoConversationBranches,
    bounded_branch_runs,
)
from tests.api.test_agent_sessions import token_for
from tests.api.test_health import build_settings, use_signing_key
from tests.browser.test_postgres_leases import database_url as database_url


def synthetic_run(identifier: str, scope: str) -> RunOutput:
    return RunOutput(
        run_id=identifier,
        agent_id="careeract-agent",
        user_id="branch-owner",
        session_id="conversation:source",
        status=RunStatus.completed,
        metadata={"career_scope": scope, "career_proposals": [{"id": "excluded"}]},
        messages=[
            Message(id=identifier + "-user", role="user", content="合成问题 " + identifier),
            Message(role="system", content="do not copy"),
            Message(role="assistant", content="tool instruction", tool_calls=[{"id": "call"}]),
            Message(role="tool", content="private tool trace"),
            Message(id=identifier + "-answer", role="assistant", content="合成答案 " + identifier),
        ],
        created_at=int(time.time()),
    )


def test_exact_branch_boundary_excludes_later_history_tools_summary_and_old_scope() -> None:
    source = AgentSession(
        session_id="conversation:source",
        user_id="branch-owner",
        agent_id="careeract-agent",
        runs=[
            synthetic_run("old", "different"),
            synthetic_run("first", "scope"),
            synthetic_run("second", "scope"),
        ],
    )
    before = bounded_branch_runs(
        source, "second-user", "before", "scope", "new", "new-scope", uuid4()
    )
    assert len(before) == 1
    assert [message.content for message in before[0].messages] == [
        "合成问题 first",
        "合成答案 first",
    ]
    assert before[0].metadata["career_scope"] == "new-scope"
    assert "career_proposals" not in before[0].metadata
    assert before[0].tools is None
    assert before[0].run_id != "first"
    assert source.runs[1].run_id == "first"
    after = bounded_branch_runs(
        source, "first-answer", "after", "scope", "new", "new-scope", uuid4()
    )
    assert len(after) == 1
    empty = bounded_branch_runs(
        source, "first-user", "before", "scope", "new", "new-scope", uuid4()
    )
    assert empty == []
    with pytest.raises(WorkSessionConflict):
        bounded_branch_runs(source, "old-answer", "after", "scope", "new", "new-scope", uuid4())


@pytest.mark.asyncio
async def test_failed_framework_save_is_not_reported_as_success() -> None:
    database = SimpleNamespace(
        upsert_session=lambda **kwargs: None, upsert_run=lambda **kwargs: None
    )
    agent = SimpleNamespace(db=database, aget_session=AsyncMock(return_value=None))
    runtime = AgnoConversationBranches(cast(Any, None), cast(Any, None), agent)
    with pytest.raises(WorkSessionHistoryUnavailable):
        await runtime.save(AgentSession(session_id="synthetic", user_id="branch-owner"))


@pytest.mark.skipif(
    os.environ.get("RUN_PROJECT_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL branches",
)
@pytest.mark.asyncio
async def test_branch_ownership_idempotency_lock_and_real_framework_history(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, key)
    settings = build_settings().model_copy(update={"database_url": PostgresDsn(database_url)})
    database = PostgresDb(
        db_url=database_url.replace("+asyncpg", "+psycopg"), db_schema="branch_test"
    )
    agent = Agent(id="careeract-agent", db=database, telemetry=False)

    class Runtime:
        agents = [agent]

        def get_app(self) -> FastAPI:
            return FastAPI()

    app = create_app(settings, lambda _: Runtime())
    engine = create_async_engine(database_url)
    owner = {"Authorization": "Bearer " + token_for(key, "branch-owner")}
    other = {"Authorization": "Bearer " + token_for(key, "branch-other")}
    try:
        async with engine.begin() as connection:
            for owner_id in ("branch-owner", "branch-other"):
                await connection.execute(
                    text(
                        'INSERT INTO auth."user" (id,name,email,"emailVerified") '
                        "VALUES (:id,:id,:email,false)"
                    ),
                    {"id": owner_id, "email": owner_id + "@example.invalid"},
                )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            source = (
                await client.post(
                    "/api/v1/agent/conversations",
                    headers=owner,
                    json={"id": str(uuid4()), "title": "合成分支来源"},
                )
            ).json()
            async with engine.connect() as connection:
                scope = str(
                    await connection.scalar(
                        text(
                            "SELECT context_version FROM career.agent_work_sessions "
                            "WHERE session_id=:id"
                        ),
                        {"id": source["session_id"]},
                    )
                )
            runs = [synthetic_run("first", scope), synthetic_run("second", scope)]
            session = AgentSession(
                session_id=source["session_id"],
                agent_id=agent.id,
                user_id="branch-owner",
                session_data={},
                created_at=int(time.time()),
                runs=runs,
            )
            await asyncio.to_thread(database.upsert_session, session=session)
            for index, run in enumerate(runs):
                await asyncio.to_thread(
                    database.upsert_run,
                    run=run,
                    session_id=session.session_id,
                    user_id=session.user_id,
                    run_index=index,
                )
            path = f"/api/v1/agent/conversations/{session.session_id}/branch"
            body = {
                "id": str(uuid4()),
                "version": source["version"],
                "message_id": "first-answer",
                "mode": "after",
                "title": "合成分支",
            }
            assert (await client.post(path, headers=other, json=body)).status_code == 404
            assert (
                await client.post(path, headers=owner, json={**body, "version": str(uuid4())})
            ).status_code == 409
            async with engine.connect() as connection:
                await lock_runtime(connection, "careeract_conversation", session.session_id)
                assert (await client.post(path, headers=owner, json=body)).status_code == 409
                await unlock_runtime(connection, "careeract_conversation", session.session_id)
            created = await client.post(path, headers=owner, json=body)
            assert created.status_code == 201, created.text
            target = created.json()
            history = await client.get(
                "/api/v1/agent/session/history",
                headers=owner,
                params={"session_id": target["session_id"]},
            )
            assert history.status_code == 200, history.text
            assert [item["content"] for item in history.json()["messages"]] == [
                "合成问题 first",
                "合成答案 first",
            ]
            assert (await client.post(path, headers=owner, json=body)).json()[
                "session_id"
            ] == target["session_id"]
            assert (
                await client.post(path, headers=owner, json={**body, "message_id": "second-answer"})
            ).status_code == 409
            assert (
                await client.get(
                    "/api/v1/agent/session/history",
                    headers=other,
                    params={"session_id": target["session_id"]},
                )
            ).status_code == 404
            empty = await client.post(
                path,
                headers=owner,
                json={**body, "id": str(uuid4()), "mode": "before", "message_id": "second-user"},
            )
            assert empty.status_code == 201, empty.text
            assert (
                await client.get(
                    "/api/v1/agent/session/history",
                    headers=owner,
                    params={"session_id": empty.json()["session_id"]},
                )
            ).json()["messages"][0]["content"] == "合成问题 first"
            assert (
                await client.post(
                    path,
                    headers=owner,
                    json={**body, "id": str(uuid4()), "mode": "before", "message_id": "first-user"},
                )
            ).status_code == 422
            occupied_id = uuid4()
            await asyncio.to_thread(
                database.upsert_session,
                session=AgentSession(
                    session_id=f"conversation:{occupied_id}",
                    user_id="branch-other",
                    created_at=int(time.time()),
                ),
            )
            assert (
                await client.post(path, headers=owner, json={**body, "id": str(occupied_id)})
            ).status_code == 409
    finally:
        await engine.dispose()
