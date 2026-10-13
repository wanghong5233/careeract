from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.api.application.boss_connections import BossConnectionService
from services.api.application.boss_login import BossLoginService
from services.api.application.boss_saved_login_viewer import BossSavedLoginViewerService
from services.api.application.context import ActorContext
from services.api.application.ports.boss_page import BossPageObservation, BossPageReader
from services.api.application.ports.browser_control import BrowserSessionControl
from services.api.application.read_execution import ReadExecutionService
from services.api.domain.boss_connection import BossConnection, BossConnectionStatus
from services.api.domain.boss_saved_login_viewer import BossSavedLoginViewer
from services.api.domain.execution import (
    AttemptStatus,
    AuthorizationStatus,
    LoginExecution,
    ReadExecution,
    TaskStatus,
)

router = APIRouter(prefix="/api/v1/connections/boss", tags=["connections"])


class StartConnectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunReadBody(StartConnectionBody):
    pass


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


class StartReadBody(RevokeConnectionBody):
    authorize_read: Literal[True]
    human_control: bool = Field(default=False, strict=True)
    conversation_id: str | None = Field(
        default=None, min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$"
    )

    @field_validator("authorize_read", mode="before")
    @classmethod
    def require_explicit_authorization(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit read authorization required")
        return value


class ReadExecutionResponse(BaseModel):
    task_id: UUID
    task_status: TaskStatus
    scope: Literal["boss.read"]
    authorization_expires_at: str
    authorization_status: AuthorizationStatus
    attempt_status: AttemptStatus
    browser_session_id: UUID | None
    outcome: str | None


class ReadResultResponse(BaseModel):
    task_id: UUID
    observed_at: str
    page: BossPageObservation


def get_read_service(request: Request) -> ReadExecutionService:
    return cast(ReadExecutionService, request.app.state.read_execution_service)


def serialize_read(execution: ReadExecution) -> ReadExecutionResponse:
    return ReadExecutionResponse(
        task_id=execution.task.id,
        task_status=execution.task.status,
        scope="boss.read",
        authorization_expires_at=execution.authorization.expires_at.isoformat(),
        authorization_status=execution.authorization.status,
        attempt_status=execution.attempt.status,
        browser_session_id=execution.attempt.browser_session_id,
        outcome=execution.attempt.outcome,
    )


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


class SavedLoginViewerResponse(BaseModel):
    id: UUID
    browser_session_id: UUID
    status: Literal["starting", "live", "closing", "released", "failed"]
    expires_at: str
    expired: bool


def get_saved_login_viewer_service(request: Request) -> BossSavedLoginViewerService:
    service = getattr(request.app.state, "boss_saved_login_viewer_service", None)
    if service is None:
        raise HTTPException(503, "Saved login viewer is not configured")
    return cast(BossSavedLoginViewerService, service)


def serialize_saved_login_viewer(viewer: BossSavedLoginViewer) -> SavedLoginViewerResponse:
    return SavedLoginViewerResponse(
        id=viewer.id,
        browser_session_id=viewer.browser_session_id,
        status=viewer.status,
        expires_at=viewer.expires_at.isoformat(),
        expired=viewer.expires_at <= datetime.now(UTC),
    )


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


@router.post("/{connection_id}/read", response_model=ReadExecutionResponse, status_code=201)
async def accept_read(
    connection_id: UUID,
    body: StartReadBody,
    response: Response,
    service: Annotated[ReadExecutionService, Depends(get_read_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> ReadExecutionResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_read(
        await service.accept_boss(
            actor,
            connection_id=connection_id,
            expected_version=body.version,
            request_key=idempotency_key,
            conversation_id=body.conversation_id,
            human_control=body.human_control,
        )
    )


@router.get("/{connection_id}/read/{task_id}", response_model=ReadExecutionResponse)
async def read_execution(
    connection_id: UUID,
    task_id: UUID,
    response: Response,
    service: Annotated[ReadExecutionService, Depends(get_read_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ReadExecutionResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_read(await service.read_boss(actor, connection_id, task_id))


@router.get("/{connection_id}/read", response_model=ReadExecutionResponse | None)
async def latest_read_execution(
    connection_id: UUID,
    response: Response,
    service: Annotated[ReadExecutionService, Depends(get_read_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ReadExecutionResponse | None:
    response.headers["Cache-Control"] = "no-store"
    execution = await service.latest_boss(actor, connection_id)
    return serialize_read(execution) if execution is not None else None


@router.post("/{connection_id}/read/{task_id}/run", response_model=ReadExecutionResponse)
async def run_read_execution(
    connection_id: UUID,
    task_id: UUID,
    body: RunReadBody,
    response: Response,
    request: Request,
    service: Annotated[ReadExecutionService, Depends(get_read_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ReadExecutionResponse:
    control = getattr(request.app.state, "browser_control", None)
    reader = getattr(request.app.state, "boss_page_reader", None)
    if control is None or reader is None:
        raise HTTPException(503, "Browser read execution is not configured")
    response.headers["Cache-Control"] = "no-store"
    return serialize_read(
        await service.execute_boss(
            actor,
            connection_id,
            task_id,
            control=cast(BrowserSessionControl, control),
            page_reader=cast(BossPageReader, reader),
        )
    )


@router.post("/{connection_id}/read/{task_id}/handback", response_model=ReadExecutionResponse)
async def handback_read_execution(
    connection_id: UUID,
    task_id: UUID,
    body: RunReadBody,
    response: Response,
    request: Request,
    service: Annotated[ReadExecutionService, Depends(get_read_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ReadExecutionResponse:
    control = getattr(request.app.state, "browser_control", None)
    reader = getattr(request.app.state, "boss_page_reader", None)
    if control is None or reader is None:
        raise HTTPException(503, "Browser handback is not configured")
    response.headers["Cache-Control"] = "no-store"
    return serialize_read(
        await service.handback_boss(
            actor,
            connection_id,
            task_id,
            control=cast(BrowserSessionControl, control),
            page_reader=cast(BossPageReader, reader),
        )
    )


@router.post("/{connection_id}/read/{task_id}/reconcile", response_model=ReadExecutionResponse)
async def reconcile_read_execution(
    connection_id: UUID,
    task_id: UUID,
    body: RunReadBody,
    response: Response,
    request: Request,
    service: Annotated[ReadExecutionService, Depends(get_read_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ReadExecutionResponse:
    control = getattr(request.app.state, "browser_control", None)
    if control is None:
        raise HTTPException(503, "Browser read execution is not configured")
    response.headers["Cache-Control"] = "no-store"
    return serialize_read(
        await service.reconcile_boss(
            actor, connection_id, task_id, control=cast(BrowserSessionControl, control)
        )
    )


@router.get("/{connection_id}/read/{task_id}/result", response_model=ReadResultResponse | None)
async def read_page_result(
    connection_id: UUID,
    task_id: UUID,
    response: Response,
    service: Annotated[ReadExecutionService, Depends(get_read_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ReadResultResponse | None:
    response.headers["Cache-Control"] = "no-store"
    result = await service.boss_result(actor, connection_id, task_id)
    return (
        ReadResultResponse(
            task_id=task_id, observed_at=result.observed_at.isoformat(), page=result.page
        )
        if result
        else None
    )


@router.delete("/{connection_id}/read/{task_id}", response_model=ReadExecutionResponse)
async def cancel_read_execution(
    connection_id: UUID,
    task_id: UUID,
    response: Response,
    request: Request,
    service: Annotated[ReadExecutionService, Depends(get_read_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ReadExecutionResponse:
    response.headers["Cache-Control"] = "no-store"
    control = cast(
        BrowserSessionControl | None, getattr(request.app.state, "browser_control", None)
    )
    return serialize_read(await service.cancel_boss(actor, connection_id, task_id, control=control))


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


@router.get("/{connection_id}/saved-login/viewer", response_model=SavedLoginViewerResponse | None)
async def read_saved_login_viewer(
    connection_id: UUID,
    response: Response,
    service: Annotated[BossSavedLoginViewerService, Depends(get_saved_login_viewer_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> SavedLoginViewerResponse | None:
    response.headers["Cache-Control"] = "no-store"
    current = await service.read(actor, connection_id)
    return serialize_saved_login_viewer(current) if current is not None else None


@router.post("/{connection_id}/saved-login/viewer", response_model=SavedLoginViewerResponse)
async def open_saved_login_viewer(
    connection_id: UUID,
    body: RevokeConnectionBody,
    response: Response,
    service: Annotated[BossSavedLoginViewerService, Depends(get_saved_login_viewer_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> SavedLoginViewerResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_saved_login_viewer(
        await service.open(actor, connection_id, expected_connection_version=body.version)
    )


@router.delete(
    "/{connection_id}/saved-login/viewer", response_model=SavedLoginViewerResponse | None
)
async def close_saved_login_viewer(
    connection_id: UUID,
    body: RevokeConnectionBody,
    response: Response,
    service: Annotated[BossSavedLoginViewerService, Depends(get_saved_login_viewer_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> SavedLoginViewerResponse | None:
    response.headers["Cache-Control"] = "no-store"
    viewer = await service.close(actor, connection_id, expected_connection_version=body.version)
    return serialize_saved_login_viewer(viewer) if viewer is not None else None
