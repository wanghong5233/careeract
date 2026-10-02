import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from agno.run.base import RunContext

from services.api.domain.profile import ProfileContent
from services.api.infrastructure.agent_tools import build_agent_tools


class FakeProfileService:
    async def read(self, actor: Any) -> Any:
        self.actor = actor
        return SimpleNamespace(
            version=uuid4(),
            confirmed_at=datetime.now(UTC),
            content=ProfileContent(
                display_name="合成用户",
                skills="Python",
                goals="合成目标",
                constraints="合成约束",
            ),
        )


class FakeProjectService:
    async def read(self, actor: Any, project_id: Any) -> Any:
        self.actor = actor
        return SimpleNamespace(
            id=project_id,
            version=uuid4(),
            title="合成项目",
            purpose="合成用途",
            status="active",
        )


class FakeMemoryService:
    def __init__(self) -> None:
        self.created: tuple[Any, dict[str, Any]] | None = None

    async def list(self, actor: Any, **kwargs: Any) -> Any:
        self.actor = actor
        if kwargs["kind"] == "rule":
            items = [
                SimpleNamespace(
                    id=uuid4(),
                    version=uuid4(),
                    kind="rule",
                    state="confirmed",
                    title="合成规则",
                    content="先核对来源",
                    source="合成来源",
                    project_id=None,
                )
            ]
        else:
            items = []
        return SimpleNamespace(items=items)

    async def create(self, actor: Any, **kwargs: Any) -> Any:
        self.created = (actor, kwargs)
        return SimpleNamespace(
            id=uuid4(),
            version=uuid4(),
            kind=kwargs["kind"],
            state="candidate",
            title=kwargs["title"],
            content=kwargs["content"],
            source=kwargs["source"],
            project_id=kwargs["project_id"],
        )


class FakeSessionService:
    async def read(self, actor: Any, session_id: str) -> Any:
        self.actor = actor
        return SimpleNamespace(project_id=uuid4())


@pytest.mark.asyncio
async def test_context_tool_uses_authenticated_run_and_returns_versions() -> None:
    profile = FakeProfileService()
    project = FakeProjectService()
    memories = FakeMemoryService()
    sessions = FakeSessionService()
    tools = build_agent_tools(profile, project, memories, sessions)(
        run_context=RunContext(run_id="run-1", session_id="session-1", user_id="user-1")
    )

    result = json.loads(await tools[0]())

    assert result["status"] == "ok"
    assert result["profile"]["content"]["goals"] == "合成目标"
    assert result["confirmed_rules"][0]["state"] == "confirmed"
    assert profile.actor.user_id == "user-1"
    assert memories.actor.user_id == "user-1"
    assert "run-1" not in result["profile"]


@pytest.mark.asyncio
async def test_proposal_is_candidate_and_uses_current_project() -> None:
    profile = FakeProfileService()
    project = FakeProjectService()
    memories = FakeMemoryService()
    sessions = FakeSessionService()
    tools = build_agent_tools(profile, project, memories, sessions)(
        run_context=RunContext(run_id="run-2", session_id="session-2", user_id="user-2")
    )

    result = json.loads(await tools[1]("合成提议", "合成内容"))

    assert result["status"] == "candidate"
    assert "确认" in result["message"]
    assert memories.created is not None
    actor, created = memories.created
    assert actor.user_id == "user-2"
    assert created["kind"] == "rule"
    assert created["project_id"] is not None
    assert created["source"] == "职业伙伴提议"
