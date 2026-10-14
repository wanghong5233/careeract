from typing import Literal, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/internal/recruiting", include_in_schema=False)


class RecruitingExecutor(Protocol):
    async def automation_step(self, reference: str) -> int: ...
    async def halt_automation(self, reference: str) -> None: ...
    async def generate(self, reference: str) -> None: ...

    async def read(self, reference: str) -> None: ...

    async def stop_read(self, reference: str) -> None: ...

    async def send_reply(self, reference: str) -> None: ...

    async def reconcile_send(self, reference: str) -> None: ...


@router.post("/{action}/{reference}", status_code=204)
async def execute(
    action: Literal[
        "generate",
        "read",
        "stop-read",
        "send",
        "cleanup-send",
        "automation-step",
        "automation-halt",
    ],
    reference: UUID,
    request: Request,
) -> Response:
    # This service credential can execute recorded tasks, never supply an actor,
    # content, target or permission. Product JWTs cannot reach this endpoint.
    if getattr(request.state, "recruiting_worker", False) is not True:
        return Response(status_code=401)
    if request.query_params:
        return Response(status_code=400)
    async for chunk in request.stream():
        if chunk:
            return Response(status_code=400)
    executor = cast(RecruitingExecutor, request.app.state.recruiting_execution)
    if action == "automation-step":
        delay = await executor.automation_step(str(reference))
        return Response(
            status_code=204,
            headers={"Cache-Control": "no-store", "X-Next-Step-Seconds": str(delay)},
        )
    actions = {
        "generate": executor.generate,
        "read": executor.read,
        "stop-read": executor.stop_read,
        "send": executor.send_reply,
        "cleanup-send": executor.reconcile_send,
        "automation-halt": executor.halt_automation,
    }
    await actions[action](str(reference))
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
