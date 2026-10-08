from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from services.api.application.context import ActorContext
from services.api.application.ports.browser_control import BrowserControlContext
from services.api.domain.execution import (
    ExecutionAttempt,
    ExecutionAuthorization,
    ExecutionTask,
    LoginExecution,
)


class ExecutionRepository(Protocol):
    async def accept(
        self,
        actor: ActorContext,
        *,
        connection_id: UUID,
        kind: str,
        request_key: UUID,
        scope: str,
        authorization_expires_at: datetime,
        request_id: UUID,
        expected_version: UUID | None = None,
    ) -> tuple[ExecutionTask, ExecutionAuthorization, ExecutionAttempt]: ...

    async def read_attempt(
        self, actor: ActorContext, attempt_id: UUID
    ) -> ExecutionAttempt | None: ...

    async def bind_browser_session(
        self, actor: ActorContext, attempt_id: UUID, session_id: UUID
    ) -> BrowserControlContext: ...

    async def record_registration(
        self,
        actor: ActorContext,
        attempt_id: UUID,
        outcome: Literal["browser_registered", "registration_unconfirmed", "registration_rejected"],
    ) -> ExecutionAttempt: ...

    async def revoke(
        self, actor: ActorContext, attempt_id: UUID, *, expected_version: UUID | None = None
    ) -> ExecutionAttempt: ...

    async def read_login(
        self, actor: ActorContext, connection_id: UUID
    ) -> LoginExecution | None: ...

    async def reserve_creation(
        self, actor: ActorContext, attempt_id: UUID
    ) -> BrowserControlContext: ...

    async def record_creation(
        self,
        actor: ActorContext,
        attempt_id: UUID,
        outcome: Literal["browser_created", "creation_unconfirmed", "creation_rejected"],
    ) -> ExecutionAttempt: ...

    async def record_release(
        self, actor: ActorContext, attempt_id: UUID, *, login_verified: bool = False
    ) -> ExecutionAttempt: ...
