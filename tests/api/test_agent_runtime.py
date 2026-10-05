from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import agno.os.interfaces.agui.router as agui_router
import httpx
import pytest
from ag_ui.core import EventType, RunAgentInput, RunFinishedEvent
from agno.os.interfaces.agui.router import run_entity
from agno.run.base import RunContext
from fastapi import FastAPI, Request

from services.api.application.context import ActorContext
from services.api.infrastructure.agent_execution import AgentExecution
from services.api.infrastructure.agent_stream import BackgroundTextAgent, CareerAGUI


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


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["COMPLETED", "CANCELLED", "ERROR", None])
async def test_stream_terminal_uses_stored_string_status(
    status: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import services.api.infrastructure.agent_stream as stream_module

    @asynccontextmanager
    async def accept(*_: object) -> AsyncIterator[None]:
        yield

    async def events(*_: object, **__: object) -> AsyncIterator[RunFinishedEvent]:
        yield RunFinishedEvent(
            type=EventType.RUN_FINISHED, thread_id="conversation:synthetic", run_id="run"
        )

    agent: Any = AsyncMock()
    agent.aget_run_output.return_value = SimpleNamespace(status=status)
    app = FastAPI()
    app.state.agent_execution = SimpleNamespace(accept=accept)

    @app.middleware("http")
    async def actor(request: Request, call_next: Any) -> Any:
        request.state.user_id = "synthetic-owner"
        return await call_next(request)

    app.include_router(CareerAGUI(agent).get_router())
    monkeypatch.setattr(stream_module, "run_entity", events)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/agui",
            json={
                "threadId": "conversation:synthetic",
                "runId": "run",
                "messages": [],
                "tools": [],
                "context": [],
                "forwardedProps": {},
            },
        )
    assert response.status_code == 200
    assert ('"type":"RUN_FINISHED"' in response.text) is (status == "COMPLETED")
    assert ('"type":"RUN_ERROR"' in response.text) is (status != "COMPLETED")


@pytest.mark.asyncio
async def test_cancel_stored_terminal_status_does_not_recancel() -> None:
    agent = AsyncMock()
    agent.aget_run_output.return_value = SimpleNamespace(
        session_id="conversation:synthetic", user_id="synthetic-owner", status="CANCELLED"
    )
    sessions = AsyncMock()
    execution = AgentExecution(AsyncMock(), sessions, agent)
    assert (
        await execution.cancel(
            ActorContext("synthetic-owner", "request"), "conversation:synthetic", "run"
        )
        == "CANCELLED"
    )
    agent.acancel_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_uses_admitted_model_and_releases_failed_preparation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.api.infrastructure.agent_stream as stream_module
    from services.api.domain.work_session import WorkSessionInvalid

    released: list[bool] = []

    @asynccontextmanager
    async def accept(*_: object) -> AsyncIterator[Any]:
        try:
            yield SimpleNamespace(model_id="selected-model")
        finally:
            released.append(True)

    captured: list[Any] = []

    async def events(agent: Any, *_: object, **__: object) -> AsyncIterator[Any]:
        captured.append(agent.agent)
        yield RunFinishedEvent(
            type=EventType.RUN_FINISHED, thread_id="conversation:synthetic", run_id="run"
        )

    original, selected = AsyncMock(), AsyncMock()
    original.aget_run_output.return_value = SimpleNamespace(status="COMPLETED")
    catalog = AsyncMock()
    catalog.agent_for = lambda agent, model: selected
    app = FastAPI()
    app.state.agent_execution = SimpleNamespace(accept=accept)
    app.state.agent_models = catalog
    app.state.settings = SimpleNamespace(litellm_model="default")

    @app.middleware("http")
    async def actor(request: Request, call_next: Any) -> Any:
        request.state.user_id = "synthetic-owner"
        return await call_next(request)

    app.include_router(CareerAGUI(original).get_router())
    monkeypatch.setattr(stream_module, "run_entity", events)
    payload = {
        "threadId": "conversation:synthetic",
        "runId": "run",
        "messages": [],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/agui", json=payload)).status_code == 200
        assert captured == [selected] and released == [True]
        catalog.require.assert_awaited_once_with("selected-model")
        catalog.require.side_effect = WorkSessionInvalid("unsupported")
        with pytest.raises(WorkSessionInvalid):
            await client.post("/agui", json=payload)
        assert released == [True, True] and captured == [selected]
