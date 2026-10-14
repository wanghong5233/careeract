from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.api.application.context import ActorContext
from services.api.application.recruiting_automation import RecruitingAutomationService
from services.api.domain.recruiting_automation import RecruitingAutomation
from services.api.routes.boss_connections import get_actor

router = APIRouter(prefix="/api/v1/recruiting/automations", tags=["recruiting"])


class CreateAutomation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: UUID
    version: UUID
    conversation_ids: list[
        Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")]
    ] = Field(min_length=1, max_length=20)
    max_sends: int = Field(ge=1, le=20)
    duration_minutes: int = Field(ge=1, le=480)
    interval_seconds: int = Field(ge=300, le=3600)
    authorize_replies: Literal[True]
    disclose_to_model: Literal[True]

    @field_validator("authorize_replies", "disclose_to_model", mode="before")
    @classmethod
    def explicit(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit delegation and model disclosure required")
        return value


class StopAutomation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: UUID


def get_service(request: Request) -> RecruitingAutomationService:
    return cast(RecruitingAutomationService, request.app.state.recruiting_automation_service)


@router.get("", response_model=RecruitingAutomation | None)
async def latest(
    connection_id: UUID,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[RecruitingAutomationService, Depends(get_service)],
) -> RecruitingAutomation | None:
    response.headers["Cache-Control"] = "no-store"
    return await service.latest(actor, connection_id)


@router.post("", response_model=RecruitingAutomation, status_code=201)
async def create(
    body: CreateAutomation,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[RecruitingAutomationService, Depends(get_service)],
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> RecruitingAutomation:
    response.headers["Cache-Control"] = "no-store"
    return await service.accept(
        actor,
        body.connection_id,
        body.version,
        key,
        tuple(body.conversation_ids),
        body.max_sends,
        body.duration_minutes,
        body.interval_seconds,
    )


@router.delete("/{reference}", response_model=RecruitingAutomation)
async def stop(
    reference: UUID,
    body: StopAutomation,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[RecruitingAutomationService, Depends(get_service)],
) -> RecruitingAutomation:
    response.headers["Cache-Control"] = "no-store"
    return await service.stop(actor, reference, body.version)


@router.post("/{reference}/dispatch", response_model=RecruitingAutomation)
async def dispatch(
    reference: UUID,
    response: Response,
    actor: Annotated[ActorContext, Depends(get_actor)],
    service: Annotated[RecruitingAutomationService, Depends(get_service)],
) -> RecruitingAutomation:
    response.headers["Cache-Control"] = "no-store"
    return await service.resume_dispatch(actor, reference)
