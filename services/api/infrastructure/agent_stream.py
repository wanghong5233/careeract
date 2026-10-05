import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Any, cast

from ag_ui.core import EventType, RunAgentInput, RunErrorEvent
from ag_ui.encoder import EventEncoder
from agno.agent import Agent
from agno.os.interfaces.agui import AGUI
from agno.os.interfaces.agui.router import run_entity
from agno.run.agent import run_output_event_from_dict
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from services.api.application.context import ActorContext
from services.api.infrastructure.agent_execution import AgentExecution


class BackgroundTextAgent:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    def arun(self, **kwargs: Any) -> AsyncIterator[Any]:
        async def events() -> AsyncIterator[Any]:
            source = self.agent.arun(**kwargs, background=True)
            async with aclosing(source) as stream:
                async for block in stream:
                    for line in block.splitlines():
                        if line.startswith("data:"):
                            yield run_output_event_from_dict(json.loads(line[5:]))

        return events()


class CareerAGUI:
    type = "agui"

    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        self.team = None
        self.workflow = None
        self.prefix = ""
        self.tags = ["AGUI"]
        self._base: Any = AGUI(agent=agent)
        self._streams: set[asyncio.Task[None]] = set()

    def get_router(self, use_async: bool = True, **kwargs: object) -> APIRouter:
        router = cast(APIRouter, self._base.get_router())
        original = next(route for route in router.routes if getattr(route, "path", None) == "/agui")
        router.routes.remove(original)

        @router.post("/agui", name="career_text_run")
        async def text_run(request: Request, run_input: RunAgentInput) -> StreamingResponse:
            execution: AgentExecution = request.app.state.agent_execution
            actor = ActorContext(request.state.user_id, run_input.run_id)
            admission = execution.accept(actor, run_input.thread_id, run_input.run_id)
            session = await admission.__aenter__()
            runtime_agent = self.agent
            prepared = False
            try:
                if session is not None:
                    catalog = request.app.state.agent_models
                    model = await catalog.require(
                        session.model_id or request.app.state.settings.litellm_model
                    )
                    runtime_agent = catalog.agent_for(self.agent, model)
                prepared = True
            finally:
                if not prepared:
                    await admission.__aexit__(None, None, None)
            encoder = EventEncoder()

            queue: asyncio.Queue[str | None] = asyncio.Queue()
            disconnected = False

            async def produce() -> None:
                try:
                    async with aclosing(
                        run_entity(
                            BackgroundTextAgent(runtime_agent), run_input, user_id=actor.user_id
                        )
                    ) as stream:
                        async for event in stream:
                            if event.type == EventType.RUN_ERROR:
                                event = RunErrorEvent(
                                    type=EventType.RUN_ERROR,
                                    message="本次运行失败，请核对已保存内容后重试。",
                                )
                            elif event.type == EventType.RUN_FINISHED:
                                output = await self.agent.aget_run_output(
                                    run_input.run_id,
                                    session_id=run_input.thread_id,
                                    user_id=actor.user_id,
                                )
                                value = getattr(output, "status", None)
                                status = getattr(value, "value", value)
                                if status != "COMPLETED":
                                    event = RunErrorEvent(
                                        type=EventType.RUN_ERROR,
                                        message="本次运行未完成，请重新读取已保存的状态。",
                                    )
                            if not disconnected:
                                queue.put_nowait(encoder.encode(event))
                finally:
                    try:
                        await asyncio.shield(admission.__aexit__(None, None, None))
                    finally:
                        queue.put_nowait(None)

            task = asyncio.create_task(produce())
            self._streams.add(task)

            def completed(finished: asyncio.Task[None]) -> None:
                self._streams.discard(finished)
                if not finished.cancelled():
                    finished.exception()

            task.add_done_callback(completed)

            async def events() -> AsyncIterator[str]:
                nonlocal disconnected
                try:
                    while (block := await queue.get()) is not None:
                        yield block
                    await task
                finally:
                    disconnected = True
                    while not queue.empty():
                        queue.get_nowait()

            return StreamingResponse(
                events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"}
            )

        return router

    def get_scope_mappings(self) -> dict[str, list[str]]:
        return {"POST /agui": ["agents:run"]}
