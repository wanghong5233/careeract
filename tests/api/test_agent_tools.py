import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import create_autospec
from uuid import UUID, uuid4

import pytest
from agno.agent import Agent
from agno.agent._hooks import aexecute_post_hooks, aexecute_pre_hooks
from agno.exceptions import InputCheckError
from agno.run.agent import RunInput, RunOutput
from agno.run.base import RunContext
from agno.session.agent import AgentSession
from agno.utils.callables import aresolve_callable_tools
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.application.agent_context import AgentContextService
from services.api.application.context import ActorContext
from services.api.application.memories import MemoryService
from services.api.application.profiles import ProfileService
from services.api.application.projects import ProjectService
from services.api.application.work_sessions import AgentWorkSessionService
from services.api.domain.memory import (
    MemoryNotFound,
    MemoryState,
    MemoryUnavailable,
    WorkspaceMemory,
)
from services.api.domain.profile import CareerProfile, ProfileContent
from services.api.domain.work_session import WorkSessionNotFound
from services.api.infrastructure.agent_tools import (
    build_agent_tools,
    build_career_instructions,
    initialize_run_manifest,
    persist_run_manifest,
)
from services.api.infrastructure.memories import PostgresMemoryRepository
from services.api.infrastructure.profiles import PostgresProfileRepository
from services.api.infrastructure.projects import PostgresProjectRepository
from services.api.infrastructure.work_sessions import PostgresAgentWorkSessionRepository
from tests.browser.test_postgres_leases import database_url as database_url


def sample_memory(
    *, state: MemoryState = "confirmed", project_id: UUID | None = None
) -> WorkspaceMemory:
    return WorkspaceMemory(
        id=uuid4(),
        user_id="synthetic-user",
        project_id=project_id,
        kind="rule",
        state=state,
        title="合成规则",
        content="先核对官方来源",
        source="合成来源",
        version=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def services() -> tuple[AgentContextService, Any, Any, Any, Any]:
    profiles = create_autospec(ProfileService, instance=True)
    projects = create_autospec(ProjectService, instance=True)
    memories = create_autospec(MemoryService, instance=True)
    sessions = create_autospec(AgentWorkSessionService, instance=True)
    sessions.read.return_value = SimpleNamespace(project_id=None)
    profiles.read.return_value = CareerProfile(
        "synthetic-user", ProfileContent(goals="合成职业目标"), uuid4(), datetime.now(UTC)
    )
    memories.effective_rules.return_value = (sample_memory(),)
    return (
        AgentContextService(profiles, projects, memories, sessions),
        profiles,
        projects,
        memories,
        sessions,
    )


@pytest.mark.asyncio
async def test_agno_hook_injection_persists_only_current_run_manifest() -> None:
    agent = Agent(telemetry=False)
    run = RunContext("run", "session", "synthetic-user", metadata={"career_basis": ["old"]})
    output = RunOutput(run_id=run.run_id)
    session = AgentSession(session_id="session", user_id="synthetic-user")
    async for _ in aexecute_pre_hooks(
        agent, [initialize_run_manifest], output, RunInput(input_content="合成"), session, run
    ):
        pass
    assert run.metadata == {"career_basis": [], "career_proposals": []}
    assert run.metadata is not None
    run.metadata["career_proposals"].append({"id": "synthetic", "title": "合成", "version": "v1"})
    async for _ in aexecute_post_hooks(agent, [persist_run_manifest], output, session, run):
        pass
    assert output.metadata == run.metadata


@pytest.mark.asyncio
async def test_rules_load_each_run_and_profile_is_read_only_on_demand() -> None:
    service, profiles, _, memories, _ = services()
    run = RunContext("run-1", "session", "synthetic-user")
    initialize_run_manifest(run)
    instructions = build_career_instructions(service)
    assert "先核对官方来源" in await instructions(run_context=run)
    profiles.read.assert_not_awaited()
    assert run.metadata and run.metadata["career_basis"][0]["type"] == "rule"
    tools = build_agent_tools(service)(run_context=run)
    payload = json.loads(await tools[0]())
    assert payload["profile"]["content"]["goals"] == "合成职业目标"
    assert profiles.read.await_args.args[0].user_id == "synthetic-user"
    memories.effective_rules.return_value = ()
    next_run = RunContext("run-2", "session", "synthetic-user")
    assert "先核对官方来源" not in await instructions(run_context=next_run)
    assert next_run.metadata == {"career_basis": []}


@pytest.mark.asyncio
async def test_candidate_replay_has_stable_id_and_cannot_confirm() -> None:
    service, _, _, memories, _ = services()
    memories.create.return_value = sample_memory(state="candidate")
    run = RunContext("run", "session", "synthetic-user")
    tools = build_agent_tools(service)(run_context=run)
    for _ in range(2):
        assert json.loads(await tools[1]("合成提议", "合成内容"))["status"] == "candidate"
    calls = memories.create.await_args_list
    assert calls[0].kwargs["memory_id"] == calls[1].kwargs["memory_id"]
    assert calls[0].kwargs["kind"] == "rule"
    assert calls[0].kwargs["source"] == "职业伙伴提议"
    memories.confirm.assert_not_awaited()
    memories.retire.assert_not_awaited()
    assert run.metadata and len(run.metadata["career_proposals"]) == 1


@pytest.mark.asyncio
async def test_same_user_tools_bind_each_run_separately() -> None:
    service, _, _, memories, _ = services()
    memories.create.return_value = sample_memory(state="candidate")
    agent = Agent(tools=build_agent_tools(service), cache_callables=False, telemetry=False)
    first = RunContext("first-run", "session", "synthetic-user")
    second = RunContext("second-run", "session", "synthetic-user")
    await aresolve_callable_tools(agent, first)
    await aresolve_callable_tools(agent, second)
    assert first.tools is not None and second.tools is not None
    await first.tools[1]("合成", "内容")
    await second.tools[1]("合成", "内容")
    assert memories.create.await_args_list[0].args[0].request_id == "first-run"
    assert memories.create.await_args_list[1].args[0].request_id == "second-run"
    assert first.metadata is not second.metadata
    assert first.metadata and first.metadata["career_proposals"]
    assert second.metadata and second.metadata["career_proposals"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [MemoryUnavailable("PRIVATE_MARKER"), WorkSessionNotFound("PRIVATE_MARKER")]
)
async def test_rule_load_failure_stops_before_model_and_sanitizes(failure: Exception) -> None:
    service, _, _, memories, _ = services()
    memories.effective_rules.side_effect = failure
    with pytest.raises(InputCheckError) as raised:
        await build_career_instructions(service)(
            run_context=RunContext("run", "session", "synthetic-user")
        )
    assert "PRIVATE_MARKER" not in str(raised.value)
    result = await build_agent_tools(service)(
        run_context=RunContext("run", "session", "synthetic-user")
    )[0]()
    assert json.loads(result)["status"] == "unavailable"
    assert "PRIVATE_MARKER" not in result


@pytest.mark.asyncio
async def test_privacy_and_context_overflow_fail_closed() -> None:
    service, profiles, _, memories, _ = services()
    profiles.read.return_value = CareerProfile(
        "synthetic-user", ProfileContent(goals="密码: synthetic-only"), uuid4(), datetime.now(UTC)
    )
    payload = await build_agent_tools(service)(
        run_context=RunContext("run", "session", "synthetic-user")
    )[0]()
    assert "synthetic-only" not in payload
    assert json.loads(payload)["status"] == "unavailable"
    memories.effective_rules.return_value = tuple(
        replace(sample_memory(), content="甲" * 8000) for _ in range(10)
    )
    with pytest.raises(InputCheckError):
        await build_career_instructions(service)(
            run_context=RunContext("run", "session", "synthetic-user")
        )


@pytest.mark.asyncio
async def test_known_records_cannot_cross_project_or_include_retired() -> None:
    service, _, _, memories, _ = services()
    memories.read.return_value = sample_memory(project_id=uuid4())
    with pytest.raises(MemoryNotFound):
        await service.read_note(
            ActorContext("synthetic-user", "run"), session_id="session", memory_id=uuid4()
        )
    memories.read.return_value = sample_memory(state="retired")
    with pytest.raises(MemoryNotFound):
        await service.read_note(
            ActorContext("synthetic-user", "run"), session_id="session", memory_id=uuid4()
        )


@pytest.mark.skipif(
    os.environ.get("RUN_PROJECT_POSTGRES_TESTS") != "1",
    reason="Opt-in PostgreSQL context isolation",
)
@pytest.mark.asyncio
async def test_real_context_rule_lifecycle_scope_and_long_lists(database_url: str) -> None:
    engine = create_async_engine(database_url)
    profiles = ProfileService(PostgresProfileRepository(engine))
    projects = ProjectService(PostgresProjectRepository(engine))
    memories = MemoryService(PostgresMemoryRepository(engine))
    sessions = AgentWorkSessionService(PostgresAgentWorkSessionRepository(engine))
    context = AgentContextService(profiles, projects, memories, sessions)
    first = ActorContext("context-first", "run")
    second = ActorContext("context-second", "run")
    try:
        async with engine.begin() as connection:
            for actor in (first, second):
                await connection.execute(
                    text(
                        'INSERT INTO auth."user" (id, name, email, "emailVerified") '
                        "VALUES (:id, :id, :email, false)"
                    ),
                    {"id": actor.user_id, "email": actor.user_id + "@example.invalid"},
                )
        project = await projects.create(first, title="当前项目", purpose="合成", status="active")
        other = await projects.create(first, title="其他项目", purpose="合成", status="active")
        await sessions.associate(first, session_id="context-session", project_id=project.id)
        await sessions.associate(second, session_id="other-session", project_id=None)
        rule = await context.propose_rule(
            first, session_id="context-session", title="官方来源", content="核对来源"
        )
        assert (
            await context.propose_rule(
                first, session_id="context-session", title="官方来源", content="核对来源"
            )
            == rule
        )
        assert (await context.read(first, session_id="context-session", include_profile=True))[
            "confirmed_rules"
        ] == []
        rule = await memories.confirm(first, rule.id, expected_version=rule.version)
        for index in range(30):
            await memories.create(
                first,
                memory_id=None,
                project_id=None,
                kind="rule",
                title=f"候选 {index}",
                content="合成",
                source="合成",
            )
        unrelated = await memories.create(
            first,
            memory_id=None,
            project_id=other.id,
            kind="rule",
            title="其他项目规则",
            content="不得带入当前项目",
            source="合成",
        )
        await memories.confirm(first, unrelated.id, expected_version=unrelated.version)
        payload = await context.read(first, session_id="context-session", include_profile=True)
        assert [
            item["id"] for item in cast(list[dict[str, object]], payload["confirmed_rules"])
        ] == [str(rule.id)]
        assert (await context.read(second, session_id="other-session", include_profile=True))[
            "confirmed_rules"
        ] == []
        with pytest.raises(WorkSessionNotFound):
            await context.read(second, session_id="context-session", include_profile=True)
        rule = await memories.update(
            first,
            rule.id,
            project_id=None,
            title=None,
            content="修正规则",
            expected_version=rule.version,
        )
        assert (await context.read(first, session_id="context-session", include_profile=True))[
            "confirmed_rules"
        ] == []
        rule = await memories.confirm(first, rule.id, expected_version=rule.version)
        await memories.retire(first, rule.id, expected_version=rule.version)
        assert (await context.read(first, session_id="context-session", include_profile=True))[
            "confirmed_rules"
        ] == []
    finally:
        await engine.dispose()
