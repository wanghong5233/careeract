from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, field_validator

from services.api.application.boss_connections import BossConnectionService
from services.api.application.boss_login import BossLoginService
from services.api.application.context import ActorContext
from services.api.domain.boss_connection import BossConnection, BossConnectionStatus
from services.api.domain.execution import (
    AttemptStatus,
    AuthorizationStatus,
    LoginExecution,
    TaskStatus,
)

router = APIRouter(prefix="/api/v1/connections/boss", tags=["connections"])


class StartConnectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RevokeConnectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: UUID


class StartLoginBody(RevokeConnectionBody):
    authorize_login: Literal[True]

    @field_validator("authorize_login", mode="before")
    @classmethod
    def require_explicit_authorization(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit login authorization required")
        return value


class LoginResponse(BaseModel):
    task_id: UUID
    task_status: TaskStatus
    authorization_id: UUID
    authorization_status: AuthorizationStatus
    authorization_expires_at: str
    scope: Literal["boss.login"]
    attempt_id: UUID
    attempt_status: AttemptStatus
    browser_session_id: UUID | None
    outcome: str | None


def get_login_service(request: Request) -> BossLoginService:
    service = getattr(request.app.state, "boss_login_service", None)
    if service is None:
        raise HTTPException(503, "Browser login is not configured")
    return cast(BossLoginService, service)


def serialize_login(execution: LoginExecution) -> LoginResponse:
    return LoginResponse(
        task_id=execution.task.id,
        task_status=execution.task.status,
        authorization_id=execution.authorization.id,
        authorization_status=execution.authorization.status,
        authorization_expires_at=execution.authorization.expires_at.isoformat(),
        scope="boss.login",
        attempt_id=execution.attempt.id,
        attempt_status=execution.attempt.status,
        browser_session_id=execution.attempt.browser_session_id,
        outcome=execution.attempt.outcome,
    )


class ConnectionResponse(BaseModel):
    id: UUID
    version: UUID
    platform: str
    browser_session_id: UUID | None
    status: BossConnectionStatus
    last_observed_url: str | None
    last_observed_state: str | None
    created_at: str
    updated_at: str


def get_service(request: Request) -> BossConnectionService:
    return cast(BossConnectionService, request.app.state.boss_connection_service)


def get_actor(request: Request) -> ActorContext:
    request_id = str(uuid4())
    request.state.request_id = request_id
    return ActorContext(user_id=request.state.user_id, request_id=request_id)


def serialize(connection: BossConnection) -> ConnectionResponse:
    return ConnectionResponse(
        id=connection.id,
        version=connection.version,
        platform=connection.platform,
        browser_session_id=connection.browser_session_id,
        status=connection.status,
        last_observed_url=connection.last_observed_url,
        last_observed_state=connection.last_observed_state,
        created_at=connection.created_at.isoformat(),
        updated_at=connection.updated_at.isoformat(),
    )


@router.get("", response_model=ConnectionResponse | None)
async def read_connection(
    response: Response,
    service: Annotated[BossConnectionService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ConnectionResponse | None:
    response.headers["Cache-Control"] = "no-store"
    connection = await service.read(actor)
    return serialize(connection) if connection is not None else None


@router.post("", response_model=ConnectionResponse, status_code=201)
async def start_connection(
    body: StartConnectionBody,
    response: Response,
    service: Annotated[BossConnectionService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> ConnectionResponse:
    response.headers["Cache-Control"] = "no-store"
    connection = await service.start(actor, request_key=idempotency_key)
    return serialize(connection)


@router.delete("/{connection_id}", response_model=ConnectionResponse)
async def revoke_connection(
    connection_id: UUID,
    body: RevokeConnectionBody,
    response: Response,
    service: Annotated[BossConnectionService, Depends(get_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ConnectionResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(await service.revoke(actor, connection_id, expected_version=body.version))


@router.get("/{connection_id}/login", response_model=LoginResponse | None)
async def read_login(
    connection_id: UUID,
    response: Response,
    service: Annotated[BossLoginService, Depends(get_login_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> LoginResponse | None:
    response.headers["Cache-Control"] = "no-store"
    current = await service.read(actor, connection_id)
    return serialize_login(current) if current is not None else None


@router.post("/{connection_id}/login", response_model=LoginResponse, status_code=201)
async def start_login(
    connection_id: UUID,
    body: StartLoginBody,
    response: Response,
    service: Annotated[BossLoginService, Depends(get_login_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> LoginResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_login(
        await service.start(
            actor, connection_id, expected_version=body.version, request_key=idempotency_key
        )
    )


@router.delete("/{connection_id}/login", response_model=LoginResponse)
async def stop_login(
    connection_id: UUID,
    body: RevokeConnectionBody,
    response: Response,
    service: Annotated[BossLoginService, Depends(get_login_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> LoginResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_login(await service.stop(actor, connection_id, expected_version=body.version))


@router.post("/{connection_id}/login/finish", response_model=LoginResponse)
async def finish_login(
    connection_id: UUID,
    body: RevokeConnectionBody,
    response: Response,
    service: Annotated[BossLoginService, Depends(get_login_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> LoginResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_login(
        await service.finish(actor, connection_id, expected_version=body.version)
    )


@router.delete("/{connection_id}/saved-login", status_code=204)
async def forget_login(
    connection_id: UUID,
    body: RevokeConnectionBody,
    service: Annotated[BossLoginService, Depends(get_login_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> Response:
    await service.forget(actor, connection_id, expected_version=body.version)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
