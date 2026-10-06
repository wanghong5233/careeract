import asyncio
import os
from time import time
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
from services.api.infrastructure.agent_execution import lock_runtime, unlock_runtime
from tests.api.test_agent_sessions import token_for
from tests.api.test_health import build_settings, use_signing_key
from tests.browser.test_postgres_leases import database_url as database_url


@pytest.mark.skipif(
    os.environ.get("RUN_PROJECT_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL conversation deletion",
)
@pytest.mark.asyncio
async def test_delete_verifies_owner_version_activity_and_framework_history(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, key)
    settings = build_settings().model_copy(update={"database_url": PostgresDsn(database_url)})
    db = PostgresDb(db_url=database_url.replace("+asyncpg", "+psycopg"), db_schema="delete_test")
    agent = Agent(id="careeract-agent", db=db, telemetry=False)

    class Runtime:
        agents = [agent]

        def get_app(self) -> FastAPI:
            return FastAPI()

    app = create_app(settings, lambda _: Runtime())
    engine = create_async_engine(database_url)
    headers = {"Authorization": "Bearer " + token_for(key, "delete-owner")}
    other = {"Authorization": "Bearer " + token_for(key, "delete-other")}
    try:
        async with engine.begin() as connection:
            for owner in ("delete-owner", "delete-other"):
                await connection.execute(
                    text(
                        'INSERT INTO auth."user" (id,name,email,"emailVerified") '
                        "VALUES (:id,'Synthetic',:email,false)"
                    ),
                    {"id": owner, "email": owner + "@example.invalid"},
                )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
        ) as client:
            project = (
                await client.post(
                    "/api/v1/projects",
                    json={"id": str(uuid4()), "title": "合成保留项目", "purpose": "合成"},
                )
            ).json()
            chat = (
                await client.post(
                    "/api/v1/agent/conversations",
                    json={
                        "id": str(uuid4()),
                        "title": "待删除合成对话",
                        "project_id": project["id"],
                    },
                )
            ).json()
            kept = (
                await client.post(
                    "/api/v1/agent/conversations",
                    json={"id": str(uuid4()), "title": "保留的独立对话"},
                )
            ).json()
            identifier = chat["session_id"]
            run = RunOutput(
                run_id="delete-run",
                agent_id=agent.id,
                session_id=identifier,
                user_id="delete-owner",
                status=RunStatus.completed,
                messages=[
                    Message(id="user", role="user", content="合成问题"),
                    Message(id="reply", role="assistant", content="合成历史"),
                ],
            )

            def stored_session() -> AgentSession:
                return AgentSession(
                    session_id=identifier,
                    user_id="delete-owner",
                    agent_id=agent.id,
                    runs=[run],
                    created_at=int(time()),
                    updated_at=int(time()),
                )

            async def save_run() -> None:
                await asyncio.to_thread(db.upsert_session, stored_session())
                await asyncio.to_thread(
                    db.upsert_run,
                    run=run,
                    session_id=identifier,
                    user_id="delete-owner",
                    run_index=0,
                )

            await save_run()
            assert await asyncio.to_thread(db.get_run, run.run_id) is not None
            path = f"/api/v1/agent/conversations/{identifier}"
            payload = {"version": chat["version"]}
            assert (
                await client.request("DELETE", path, json=payload, headers=other)
            ).status_code == 404
            assert (
                await client.request("DELETE", path, json={"version": str(uuid4())})
            ).status_code == 409
            async with engine.connect() as connection:
                await lock_runtime(connection, "careeract_conversation", identifier)
                await connection.commit()
                assert (await client.request("DELETE", path, json=payload)).status_code == 409
                await unlock_runtime(connection, "careeract_conversation", identifier)
            run.status = RunStatus.running
            await save_run()
            stored = await agent.aget_session(session_id=identifier, user_id="delete-owner")
            assert stored is not None
            assert [item.status for item in stored.runs or []] == [RunStatus.running]
            assert (await client.request("DELETE", path, json=payload)).status_code == 409
            run.status = RunStatus.completed
            await save_run()
            side = (
                await client.post(
                    "/api/v1/agent/side-chats",
                    json={"id": str(uuid4()), "tab_id": str(uuid4()), "source_id": identifier},
                )
            ).json()
            assert (await client.request("DELETE", path, json=payload)).status_code == 409
            assert (
                await client.post(f"/api/v1/agent/side-chats/{side['session_id']}/close", json={})
            ).status_code == 200
            original_delete = agent.adelete_session

            async def unconfirmed_delete(**_: object) -> None:
                return None

            monkeypatch.setattr(agent, "adelete_session", unconfirmed_delete)
            assert (await client.request("DELETE", path, json=payload)).status_code == 503
            assert (await client.get(path)).status_code == 200
            monkeypatch.setattr(agent, "adelete_session", original_delete)
            assert (await client.request("DELETE", path, json=payload)).json() == {
                "status": "deleted"
            }
            assert (await client.get(path)).status_code == 404
            assert (
                await client.get("/api/v1/agent/session/history", params={"session_id": identifier})
            ).status_code == 404
            assert await agent.aget_session(session_id=identifier, user_id="delete-owner") is None
            assert await asyncio.to_thread(db.get_run, run.run_id) is None
            assert (await client.get(f"/api/v1/projects/{project['id']}")).status_code == 200
            assert (
                await client.get(f"/api/v1/agent/conversations/{kept['session_id']}")
            ).status_code == 200
    finally:
        await engine.dispose()
