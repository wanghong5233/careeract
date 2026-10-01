from dataclasses import asdict
from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from services.api.application.context import ActorContext
from services.api.application.work_sessions import AgentWorkSessionService
from services.api.domain.work_session import AgentWorkSession
from services.api.infrastructure.agent_sessions import AgentHistoryReader

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class AssociateWorkSessionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    project_id: UUID | None = None


class WorkSessionResponse(BaseModel):
    session_id: str
    project_id: UUID | None
    created_at: str
    updated_at: str


class HistoryMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: int


class HistoryResponse(BaseModel):
    session: WorkSessionResponse
    messages: list[HistoryMessageResponse]


def get_service(request: Request) -> AgentWorkSessionService:
    return cast(AgentWorkSessionService, request.app.state.agent_work_session_service)


def get_history_reader(request: Request) -> AgentHistoryReader:
    reader = getattr(request.app.state, "agent_history_reader", None)
    if reader is None:
        from services.api.domain.work_session import WorkSessionHistoryUnavailable

        raise WorkSessionHistoryUnavailable("Agent history is unavailable")
    return cast(AgentHistoryReader, reader)


def get_actor(request: Request) -> ActorContext:
    request_id = str(uuid4())
    request.state.request_id = request_id
    return ActorContext(user_id=request.state.user_id, request_id=request_id)


def serialize_session(session: AgentWorkSession) -> WorkSessionResponse:
    return WorkSessionResponse(
        session_id=session.session_id,
        project_id=session.project_id,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


@router.put("/session", response_model=WorkSessionResponse)
async def associate_session(
    body: AssociateWorkSessionBody,
    response: Response,
    service: Annotated[AgentWorkSessionService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> WorkSessionResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_session(
        await service.associate(actor, session_id=body.session_id, project_id=body.project_id)
    )


@router.get("/session/history", response_model=HistoryResponse)
async def read_session_history(
    session_id: Annotated[str, Query(min_length=1, max_length=128)],
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    service: Annotated[AgentWorkSessionService, Depends(get_service)] = None,  # type: ignore[assignment]
    reader: Annotated[AgentHistoryReader, Depends(get_history_reader)] = None,  # type: ignore[assignment]
    actor: Annotated[ActorContext, Depends(get_actor)] = None,  # type: ignore[assignment]
) -> HistoryResponse:
    response.headers["Cache-Control"] = "no-store"
    session = await service.read(actor, session_id=session_id)
    messages = await reader.read(session_id=session.session_id, user_id=actor.user_id, limit=limit)
    return HistoryResponse(
        session=serialize_session(session),
        messages=[HistoryMessageResponse(**asdict(message)) for message in messages],
    )
