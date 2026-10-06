import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agno.metrics import RunMetrics, ToolCallMetrics
from agno.models.message import Message
from agno.models.response import ToolExecution
from agno.run.agent import (
    ReasoningContentDeltaEvent,
    RunOutput,
    ToolCallCompletedEvent,
    ToolCallStartedEvent,
)
from agno.run.base import RunStatus
from agno.session.agent import AgentSession

from services.api.infrastructure.agent_sessions import AgnoAgentHistoryReader
from services.api.infrastructure.agent_stream import BackgroundTextAgent
from services.api.infrastructure.run_process import tool_activity


@pytest.mark.asyncio
async def test_saved_process_reuses_agno_and_excludes_payloads_reasoning_and_history() -> None:
    tool = ToolExecution(
        tool_call_id="search",
        tool_name="search_public_web",
        tool_args={"private": "hidden"},
        result="hidden result",
        metrics=ToolCallMetrics(duration=1.2),
    )
    run = RunOutput(
        run_id="run",
        status=RunStatus.completed,
        tools=[tool],
        metrics=RunMetrics(duration=4),
        reasoning_content="hidden reasoning",
        messages=[
            Message(id="system", role="system", content="hidden system"),
            Message(id="old", role="assistant", content="hidden old", from_history=True),
            Message(id="user", role="user", content="合成目标"),
            Message(
                id="progress",
                role="assistant",
                content="我先核对公开来源。",
                tool_calls=[{"id": "search"}],
            ),
            Message(id="tool", role="tool", content="hidden result"),
            Message(id="answer", role="assistant", content="合成最终回答"),
        ],
    )
    agent = SimpleNamespace(
        aget_session=AsyncMock(return_value=AgentSession(session_id="synthetic", runs=[run]))
    )
    messages = await AgnoAgentHistoryReader(agent).read(
        session_id="synthetic", user_id="owner", limit=100
    )
    assert [message.id for message in messages] == ["user", "answer"]
    assert messages[-1].run_duration_seconds == 4
    assert messages[-1].process == (
        {"id": "progress", "kind": "message", "content": "我先核对公开来源。"},
        {
            "id": "search",
            "kind": "tool",
            "label": "检索公开网页",
            "status": "COMPLETED",
            "duration_seconds": 1.2,
        },
    )
    assert "hidden" not in str(messages)
    later = RunOutput(
        run_id="later",
        status=RunStatus.completed,
        messages=[
            Message(id="user", role="user", content="合成目标", from_history=True),
            Message(id="answer", role="assistant", content="合成最终回答", from_history=True),
            Message(id="next-user", role="user", content="合成后续"),
            Message(id="next-answer", role="assistant", content="合成后续回答"),
        ],
    )
    agent.aget_session.return_value = AgentSession(session_id="synthetic", runs=[run, later])
    history = await AgnoAgentHistoryReader(agent).read(
        session_id="synthetic", user_id="owner", limit=100
    )
    assert [message.run_id for message in history] == ["run", "run", "later", "later"]
    assert history[1].process == messages[-1].process
    agent.aget_session.return_value = AgentSession(session_id="synthetic", runs=[run])
    run.status = RunStatus.cancelled
    run.messages = run.messages[:-1]
    tool.result = None
    tool.metrics = None
    cancelled = await AgnoAgentHistoryReader(agent).read(
        session_id="synthetic", user_id="owner", limit=100
    )
    assert cancelled[-1].content == ""
    assert cancelled[-1].run_status == "CANCELLED"
    assert cancelled[-1].process[-1]["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_stream_process_sanitizes_existing_framework_events_without_altering_storage() -> (
    None
):
    source_tool = ToolExecution(
        tool_call_id="tool",
        tool_name="read_career_context",
        tool_args={"secret": "hidden"},
        result="hidden result",
        metrics=ToolCallMetrics(duration=0.8),
    )
    source_events = [
        ReasoningContentDeltaEvent(reasoning_content="hidden reasoning"),
        ToolCallStartedEvent(tool=source_tool),
        ToolCallCompletedEvent(tool=source_tool),
    ]

    async def stream(**_: object) -> AsyncIterator[str]:
        for event in source_events:
            yield "data:" + json.dumps(event.to_dict()) + "\n\n"

    projected = [event async for event in BackgroundTextAgent(SimpleNamespace(arun=stream)).arun()]
    assert len(projected) == 2
    assert projected[0].tool.tool_args == {}
    result = json.loads(projected[1].tool.result)
    assert result["label"] == "读取职业背景"
    assert result["status"] == "COMPLETED"
    assert result["duration_seconds"] == 0.8
    assert "hidden" not in str([event.to_dict() for event in projected])
    assert source_tool.result == "hidden result"


def test_tool_process_does_not_guess_success_or_expose_unknown_names() -> None:
    tool = ToolExecution(tool_call_id="tool", tool_name="private-name")
    assert tool_activity(tool, "ERROR")["status"] == "UNKNOWN"
    assert tool_activity(tool, "ERROR")["label"] == "工具调用"
    tool.tool_call_error = True
    assert tool_activity(tool, "COMPLETED")["status"] == "ERROR"
    tool.tool_call_error = False
    tool.result = '{"status":"unavailable","message":"hidden"}'
    assert tool_activity(tool, "COMPLETED")["status"] == "ERROR"
    tool.result = '{"status":"rejected"}'
    assert tool_activity(tool, "COMPLETED")["status"] == "REJECTED"
