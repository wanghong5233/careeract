from collections.abc import AsyncIterator

import agno.os.interfaces.agui.router as agui_router
import pytest
from ag_ui.core import RunAgentInput
from agno.os.interfaces.agui.router import run_entity
from agno.run.base import RunContext

from services.api.infrastructure.agent_stream import BackgroundTextAgent


class CapturingAgent:
    def __init__(self) -> None:
        self.db = None
        self.user_id = None
        self.calls: list[dict[str, object]] = []

    def arun(self, **kwargs: object) -> AsyncIterator[object]:
        self.calls.append(kwargs)

        async def stream() -> AsyncIterator[object]:
            if False:
                yield None

        return stream()


@pytest.mark.asyncio
async def test_agui_binds_conversation_to_agno_session_and_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = CapturingAgent()
    captured: dict[str, object] = {}

    async def fake_stream(
        response_stream: object, thread_id: str, run_id: str, run_state: object = None
    ) -> AsyncIterator[object]:
        captured.update(
            response_stream=response_stream,
            thread_id=thread_id,
            run_id=run_id,
            run_state=run_state,
        )
        yield {"type": "synthetic-stream"}

    monkeypatch.setattr(agui_router, "async_stream_agno_response_as_agui_events", fake_stream)
    request = RunAgentInput.model_validate(
        {
            "threadId": "conversation:synthetic",
            "runId": "run-synthetic",
            "messages": [{"id": "message-synthetic", "role": "user", "content": "合成请求"}],
            "tools": [],
            "context": [],
            "forwardedProps": {},
        }
    )

    events = [event async for event in run_entity(agent, request, user_id="synthetic-user")]

    assert len(events) == 2
    assert getattr(getattr(events[0], "type", None), "value", None) == "RUN_STARTED"
    assert events[1] == {"type": "synthetic-stream"}
    assert agent.calls[0]["session_id"] == "conversation:synthetic"
    assert agent.calls[0]["user_id"] == "synthetic-user"
    assert agent.calls[0]["run_id"] == "run-synthetic"
    context = agent.calls[0]["run_context"]
    assert isinstance(context, RunContext)
    assert context.session_id == "conversation:synthetic"
    assert context.user_id == "synthetic-user"
    assert captured["thread_id"] == "conversation:synthetic"


@pytest.mark.asyncio
async def test_background_text_agent_rehydrates_agno_sse_events() -> None:
    class SyntheticAgent:
        def arun(self, **_: object) -> AsyncIterator[str]:
            async def stream() -> AsyncIterator[str]:
                yield (
                    "event: RunStarted\n"
                    'data: {"created_at": 1, "event": "RunStarted", '
                    '"agent_id": "careeract-agent", "agent_name": "CareerAct", '
                    '"run_id": "run", "session_id": "conversation"}\n\n'
                )

            return stream()

    events = [
        event
        async for event in BackgroundTextAgent(SyntheticAgent()).arun(
            input="合成", stream=True, stream_events=True
        )
    ]
    assert events[0].event == "RunStarted"
