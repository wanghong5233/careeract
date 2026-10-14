from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.api.application.communication import CommunicationService
from services.api.application.communication_send import CommunicationSendService
from services.api.application.context import ActorContext
from services.api.domain.communication import (
    CommunicationConflict,
    CommunicationInvalid,
    CommunicationNotFound,
    CommunicationReply,
    CommunicationUnavailable,
    ReplyDecision,
    ReplyState,
)
from services.api.domain.communication_send import CommunicationSend
from services.api.routes.boss_connections import get_actor

router = APIRouter(prefix="/api/v1/recruiting/replies", tags=["recruiting"])


class CreateReplyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: UUID
    read_task_id: UUID
    conversation_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    message_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    disclose_to_model: Literal[True]

    @field_validator("disclose_to_model", mode="before")
    @classmethod
    def explicit_disclosure(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit model disclosure required")
        return value


class EmptyReplyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CancelReplyBody(EmptyReplyBody):
    version: UUID


class SendReplyBody(CancelReplyBody):
    authorize_send: Literal[True]

    @field_validator("authorize_send", mode="before")
    @classmethod
    def explicit_send(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit send authorization required")
        return value


class ReconcileSendBody(EmptyReplyBody):
    read_task_id: UUID


def get_send_service(request: Request) -> CommunicationSendService:
    return cast(CommunicationSendService, request.app.state.communication_send_service)


@router.get("/{reply_id}/send", response_model=CommunicationSend | None)
async def read_send(
    reply_id: UUID,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[CommunicationSendService, Depends(get_send_service)],
) -> CommunicationSend | None:
    response.headers["Cache-Control"] = "no-store"
    return await service.get(actor, reply_id)


@router.post("/{reply_id}/send", response_model=CommunicationSend, status_code=201)
async def authorize_send(
    reply_id: UUID,
    body: SendReplyBody,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[CommunicationSendService, Depends(get_send_service)],
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> CommunicationSend:
    response.headers["Cache-Control"] = "no-store"
    return await service.authorize(actor, reply_id, body.version, key)


@router.post("/{reply_id}/send/resume", response_model=CommunicationSend)
async def resume_send(
    reply_id: UUID,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[CommunicationSendService, Depends(get_send_service)],
) -> CommunicationSend:
    response.headers["Cache-Control"] = "no-store"
    return await service.resume(actor, reply_id)


@router.delete("/{reply_id}/send", response_model=CommunicationSend)
async def cancel_send(
    reply_id: UUID,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[CommunicationSendService, Depends(get_send_service)],
) -> CommunicationSend:
    response.headers["Cache-Control"] = "no-store"
    return await service.cancel(actor, reply_id)


@router.post("/{reply_id}/send/reconcile", response_model=CommunicationSend)
async def reconcile_send(
    reply_id: UUID,
    body: ReconcileSendBody,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[CommunicationSendService, Depends(get_send_service)],
) -> CommunicationSend:
    response.headers["Cache-Control"] = "no-store"
    return await service.reconcile(actor, reply_id, body.read_task_id)


class ReplyResponse(BaseModel):
    id: UUID
    connection_id: UUID
    read_task_id: UUID
    conversation_id: str
    message_id: str
    version: UUID
    status: ReplyState
    outcome: str | None
    decision: ReplyDecision | None
    created_at: str
    expires_at: str


def serialize(reply: CommunicationReply) -> ReplyResponse:
    return ReplyResponse(
        id=reply.id,
        connection_id=reply.connection_id,
        read_task_id=reply.read_task_id,
        conversation_id=reply.conversation_id,
        message_id=reply.message_id,
        version=reply.version,
        status=reply.status,
        outcome=reply.outcome,
        decision=reply.decision,
        created_at=reply.created_at.isoformat(),
        expires_at=reply.expires_at.isoformat(),
    )


def get_service(request: Request) -> CommunicationService:
    return cast(CommunicationService, request.app.state.communication_service)


class ReplyListResponse(BaseModel):
    items: list[ReplyResponse]
    next_cursor: UUID | None


@router.post("", response_model=ReplyResponse, status_code=201)
async def create_reply(
    body: CreateReplyBody,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[CommunicationService, Depends(get_service)],
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> ReplyResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(
        await service.accept_reply(
            actor,
            connection_id=body.connection_id,
            read_task_id=body.read_task_id,
            conversation_id=body.conversation_id,
            message_id=body.message_id,
            request_key=key,
        )
    )


@router.get("", response_model=ReplyListResponse)
async def list_replies(
    connection_id: UUID,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[CommunicationService, Depends(get_service)],
    cursor: UUID | None = None,
) -> ReplyListResponse:
    response.headers["Cache-Control"] = "no-store"
    page = await service.list(actor, connection_id, cursor)
    return ReplyListResponse(items=[serialize(r) for r in page.items], next_cursor=page.next_cursor)


@router.get("/{reply_id}", response_model=ReplyResponse)
async def read_reply(
    reply_id: UUID,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[CommunicationService, Depends(get_service)],
) -> ReplyResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(await service.get(actor, reply_id))


@router.post("/{reply_id}/resume", response_model=ReplyResponse)
async def resume_reply(
    reply_id: UUID,
    body: EmptyReplyBody,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[CommunicationService, Depends(get_service)],
) -> ReplyResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(await service.resume(actor, reply_id))


@router.delete("/{reply_id}", response_model=ReplyResponse)
async def cancel_reply(
    reply_id: UUID,
    body: CancelReplyBody,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[CommunicationService, Depends(get_service)],
) -> ReplyResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(await service.cancel(actor, reply_id, body.version))


async def communication_error(request: Request, error: Exception) -> JSONResponse:
    if isinstance(error, CommunicationNotFound):
        status, code, message = 404, "reply_not_found", "找不到这条回复任务。"
    elif isinstance(error, CommunicationConflict):
        status, code, message = (
            409,
            "reply_conflict",
            "请读取最新任务；仅能处理近期核验的未回复来信。",
        )
    elif isinstance(error, CommunicationInvalid):
        status, code, message = 422, "invalid_reply", "本次回复缺少可靠依据或超出处理范围。"
    elif isinstance(error, CommunicationUnavailable):
        status, code, message = (
            503,
            "reply_unavailable",
            "回复服务暂不可用，请读取已保存任务核对，不要重复创建。",
        )
    else:
        raise error
    return JSONResponse(
        {"error": {"code": code, "message": message, "request_id": request.state.request_id}},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )
