import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.app.factory import create_app
from services.api.application.context import ActorContext
from services.api.application.ports.work_sessions import AgentHistoryMessage
from services.api.application.work_sessions import AgentWorkSessionService
from services.api.domain.work_session import AgentWorkSession, WorkSessionUnavailable
from services.api.infrastructure.conversation_titles import AgnoConversationTitleGenerator
from tests.api.test_agent_sessions import token_for
from tests.api.test_health import build_settings, use_signing_key
from tests.browser.test_postgres_leases import database_url as database_url


def title_fixture() -> tuple[AgentWorkSessionService, AgentWorkSession, ActorContext]:
    session = AgentWorkSession(
        "conversation:synthetic",
        "synthetic",
        None,
        datetime.now(UTC),
        datetime.now(UTC),
        title="新对话",
        title_origin="default",
    )
    repository = AsyncMock()
    repository.get.return_value = session
    repository.claim_title.return_value = replace(
        session, title_generation_attempted=True, version=uuid4()
    )
    repository.save_generated_title.return_value = replace(
        session, title="合成面试准备", title_origin="generated"
    )
    service = AgentWorkSessionService(repository)
    service.history = AsyncMock()
    service.history.read.return_value = (
        AgentHistoryMessage("prompt", "user", "合成面试目标" * 1000, 1, "run", "COMPLETED"),
    )
    service.title_generator = AsyncMock()
    service.title_generator.generate.return_value = "合成面试准备"
    return service, session, ActorContext(user_id="synthetic", request_id="title-test")


@pytest.mark.asyncio
async def test_naming_uses_bounded_saved_prompt_and_preserves_manual_title() -> None:
    service, session, actor = title_fixture()
    generator = cast(AsyncMock, service.title_generator)
    repository = cast(AsyncMock, service.repository)
    result = await service.generate_title(
        actor, session_id=session.session_id, expected_version=session.version
    )
    assert result.title == "合成面试准备"
    assert len(generator.generate.call_args.args[0]) == 4000
    repository.get.return_value = replace(session, title_origin="manual")
    await service.generate_title(
        actor, session_id=session.session_id, expected_version=session.version
    )
    assert generator.generate.await_count == 1


@pytest.mark.asyncio
async def test_naming_failure_is_bounded_and_manual_rename_wins_race() -> None:
    service, session, actor = title_fixture()
    generator = cast(AsyncMock, service.title_generator)
    repository = cast(AsyncMock, service.repository)
    generator.generate.side_effect = WorkSessionUnavailable("synthetic failure")
    assert (
        await service.generate_title(
            actor, session_id=session.session_id, expected_version=session.version
        )
        == session
    )
    repository.save_generated_title.assert_not_awaited()
    generator.generate.side_effect = None
    repository.save_generated_title.return_value = None
    manual = replace(session, title="用户手动名称", title_origin="manual")
    repository.get.side_effect = [session, manual]
    assert (
        await service.generate_title(
            actor, session_id=session.session_id, expected_version=session.version
        )
        == manual
    )


@pytest.mark.asyncio
async def test_agno_naming_gets_no_tools_or_personal_context_and_never_writes_session() -> None:
    with patch("agno.agent.Agent.generate_session_name", return_value="合成面试准备") as generate:
        assert (
            await AgnoConversationTitleGenerator(build_settings()).generate("仅合成输入")
            == "合成面试准备"
        )
    session = generate.call_args.args[0]
    assert session.session_id == "title-only"
    assert [(message.role, message.content) for message in session.get_messages()] == [
        ("user", "仅合成输入")
    ]


@pytest.mark.skipif(
    os.environ.get("RUN_PROJECT_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL naming integration",
)
@pytest.mark.asyncio
async def test_title_api_ownership_single_attempt_manual_race_and_model_metadata(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    settings = build_settings().model_copy(update={"database_url": PostgresDsn(database_url)})

    class Runtime:
        def get_app(self) -> FastAPI:
            return FastAPI()

    app = create_app(settings, lambda _settings: Runtime())
    service = app.state.agent_work_session_service
    service.history = AsyncMock()
    service.history.read.return_value = (
        AgentHistoryMessage("prompt", "user", "合成面试准备", 1, "run", "COMPLETED"),
    )
    service.title_generator = AsyncMock()
    started, release = asyncio.Event(), asyncio.Event()

    async def generate(prompt: str) -> str:
        started.set()
        await release.wait()
        return "合成自动标题"

    service.title_generator.generate.side_effect = generate
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            for user_id in ["title-owner", "title-other"]:
                await connection.execute(
                    text(
                        'INSERT INTO auth."user" (id, name, email, "emailVerified") '
                        "VALUES (:id, :id, :email, false)"
                    ),
                    {"id": user_id, "email": f"{user_id}@example.invalid"},
                )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            owner = {"Authorization": f"Bearer {token_for(private_key, 'title-owner')}"}
            other = {"Authorization": f"Bearer {token_for(private_key, 'title-other')}"}
            created = (
                await client.post(
                    "/api/v1/agent/conversations", headers=owner, json={"id": str(uuid4())}
                )
            ).json()
            path = f"/api/v1/agent/conversations/{created['session_id']}"
            denied = await client.post(
                path + "/title", headers=other, json={"version": created["version"]}
            )
            assert denied.status_code == 404
            naming = asyncio.create_task(
                client.post(path + "/title", headers=owner, json={"version": created["version"]})
            )
            await asyncio.wait_for(started.wait(), timeout=5)
            claimed = (await client.get(path, headers=owner)).json()
            assert claimed["title_generation_attempted"]
            assert (
                await client.post(
                    path + "/title", headers=owner, json={"version": created["version"]}
                )
            ).status_code == 409
            renamed = await client.patch(
                path, headers=owner, json={"version": claimed["version"], "title": "新对话"}
            )
            assert renamed.status_code == 200
            assert renamed.json()["title_origin"] == "manual"
            release.set()
            assert (await naming).json()["title_origin"] == "manual"
            assert (
                await client.post(
                    path + "/title", headers=owner, json={"version": renamed.json()["version"]}
                )
            ).status_code == 200
            assert service.title_generator.generate.await_count == 1
            assert (await client.get("/api/v1/agent/model", headers=owner)).json() == {
                "id": settings.litellm_model,
                "connection": "LiteLLM",
            }
            assert (await client.get("/api/v1/agent/model")).status_code == 401
            second = (
                await client.post(
                    "/api/v1/agent/conversations", headers=owner, json={"id": str(uuid4())}
                )
            ).json()
            service.title_generator.generate.side_effect = WorkSessionUnavailable(
                "synthetic failure"
            )
            failed = await client.post(
                f"/api/v1/agent/conversations/{second['session_id']}/title",
                headers=owner,
                json={"version": second["version"]},
            )
            assert failed.status_code == 200 and failed.json()["title_generation_attempted"]
            failed_again = await client.post(
                f"/api/v1/agent/conversations/{second['session_id']}/title",
                headers=owner,
                json={"version": failed.json()["version"]},
            )
            assert failed_again.status_code == 200
            assert service.title_generator.generate.await_count == 2
    finally:
        release.set()
        await engine.dispose()
