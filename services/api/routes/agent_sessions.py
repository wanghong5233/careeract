from dataclasses import asdict
from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.api.application.context import ActorContext
from services.api.application.ports.agent_runtime import AgentExecutionPort
from services.api.application.ports.work_sessions import AgentHistoryReader
from services.api.application.work_sessions import AgentWorkSessionService
from services.api.domain.work_session import AgentWorkSession

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
    title: str
    archived: bool
    version: UUID


class WorkSessionPageResponse(BaseModel):
    items: list[WorkSessionResponse]
    next_cursor: str | None


class CreateConversationBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: UUID
    title: str = Field(default="新对话", min_length=1, max_length=120)
    project_id: UUID | None = None


class UpdateConversationBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: UUID
    title: str | None = Field(default=None, min_length=1, max_length=120)
    archived: bool | None = None
    project_id: UUID | None = None

    @model_validator(mode="after")
    def require_changes(self) -> "UpdateConversationBody":
        changes = self.model_fields_set - {"version"}
        if not changes or any(getattr(self, field) is None for field in changes - {"project_id"}):
            raise ValueError("Provide conversation changes")
        return self


class HistoryMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: int
    run_id: str | None
    run_status: str


class HistoryResponse(BaseModel):
    session: WorkSessionResponse
    messages: list[HistoryMessageResponse]
    truncated: bool
    runs: list[dict[str, str | None]] = Field(default_factory=list)


class CancelRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=128)


class ContextBasisResponse(BaseModel):
    run_id: str | None
    references: list[dict[str, str]]
    proposals: list[dict[str, str]]


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


@router.post("/conversations/{session_id}/cancel")
async def cancel_run(
    session_id: str,
    body: CancelRunBody,
    request: Request,
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> dict[str, str]:
    execution = cast(AgentExecutionPort, request.app.state.agent_execution)
    return {"status": await execution.cancel(actor, session_id, body.run_id)}


def serialize_session(session: AgentWorkSession) -> WorkSessionResponse:
    return WorkSessionResponse(
        session_id=session.session_id,
        project_id=session.project_id,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        title=session.title,
        archived=session.archived,
        version=session.version,
    )


@router.get("/conversations", response_model=WorkSessionPageResponse)
async def list_conversations(
    response: Response,
    service: Annotated[AgentWorkSessionService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    archived: bool | None = None,
) -> WorkSessionPageResponse:
    response.headers["Cache-Control"] = "no-store"
    page = await service.list(actor, cursor=cursor, limit=limit, archived=archived)
    return WorkSessionPageResponse(
        items=[serialize_session(item) for item in page.items], next_cursor=page.next_cursor
    )


@router.post("/conversations", response_model=WorkSessionResponse, status_code=201)
async def create_conversation(
    body: CreateConversationBody,
    response: Response,
    service: Annotated[AgentWorkSessionService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> WorkSessionResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_session(
        await service.create(
            actor, conversation_id=body.id, title=body.title, project_id=body.project_id
        )
    )


@router.get("/conversations/{session_id}", response_model=WorkSessionResponse)
async def read_conversation(
    session_id: str,
    response: Response,
    service: Annotated[AgentWorkSessionService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> WorkSessionResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_session(await service.read(actor, session_id=session_id))


@router.patch("/conversations/{session_id}", response_model=WorkSessionResponse)
async def update_conversation(
    session_id: str,
    body: UpdateConversationBody,
    response: Response,
    service: Annotated[AgentWorkSessionService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> WorkSessionResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_session(
        await service.update(
            actor,
            session_id=session_id,
            title=body.title,
            archived=body.archived,
            project_id=body.project_id,
            change_project="project_id" in body.model_fields_set,
            expected_version=body.version,
        )
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
    messages = await reader.read(
        session_id=session.session_id, user_id=actor.user_id, limit=limit + 1
    )
    runs = getattr(reader, "runs", None)
    return HistoryResponse(
        session=serialize_session(session),
        messages=[HistoryMessageResponse(**asdict(message)) for message in messages[-limit:]],
        truncated=len(messages) > limit,
        runs=await runs(session_id=session.session_id, user_id=actor.user_id)
        if callable(runs)
        else [],
    )


@router.get("/session/basis", response_model=ContextBasisResponse)
async def read_context_basis(
    session_id: Annotated[str, Query(min_length=1, max_length=128)],
    response: Response,
    service: Annotated[AgentWorkSessionService, Depends(get_service)],
    reader: Annotated[AgentHistoryReader, Depends(get_history_reader)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ContextBasisResponse:
    response.headers["Cache-Control"] = "no-store"
    session = await service.read(actor, session_id=session_id)
    basis = await reader.basis(session_id=session.session_id, user_id=actor.user_id)
    return ContextBasisResponse(**asdict(basis))
