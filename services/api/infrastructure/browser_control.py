from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel, ConfigDict, ValidationError

from services.api.application.ports.browser_control import (
    BrowserAction,
    BrowserControlConflict,
    BrowserControlContext,
    BrowserControlRejected,
    BrowserControlUncertain,
    BrowserLease,
    BrowserSession,
)


class LeaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    lease_id: UUID
    owner_id: str
    expires_at: datetime
    draining: bool


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    status: Literal["live", "released"]
    login_verified: bool | None = None


class BrowserCommandSigner:
    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self.private_key = private_key

    def sign(
        self, context: BrowserControlContext, action: BrowserAction, lease_id: UUID | None = None
    ) -> str:
        if (
            not context.user_id.strip()
            or not context.owner_id.strip()
            or context.authorization_expires_at.utcoffset() is None
            or (
                action in ("register", "revoke", "acquire", "viewer", "create", "release", "finish")
            )
            != (lease_id is None)
        ):
            raise BrowserControlRejected("Invalid browser control context")
        issued_at = int(datetime.now(UTC).timestamp())
        expires_at = issued_at + 60
        if action not in ("revoke", "release"):
            expires_at = min(expires_at, int(context.authorization_expires_at.timestamp()))
        if expires_at <= issued_at:
            raise BrowserControlRejected("Browser authorization has expired")
        return jwt.encode(
            {
                "iss": "careeract-api",
                "aud": "careeract-browser",
                "sub": context.user_id,
                "iat": issued_at,
                "exp": expires_at,
                "jti": str(uuid4()),
                "session_id": str(context.session_id),
                "task_id": str(context.task_id),
                "authorization_id": str(context.authorization_id),
                "attempt_id": str(context.attempt_id),
                "request_id": str(context.request_id),
                "owner_id": context.owner_id,
                "action": action,
                "lease_id": str(lease_id) if lease_id is not None else None,
            },
            self.private_key,
            algorithm="EdDSA",
        )


class BrowserControlClient:
    def __init__(self, client: httpx.AsyncClient, signer: BrowserCommandSigner) -> None:
        self.client = client
        self.signer = signer

    async def send(
        self, context: BrowserControlContext, action: BrowserAction, lease_id: UUID | None = None
    ) -> BrowserLease | None:
        if action in ("viewer", "create", "release", "finish"):
            raise BrowserControlRejected("Browser action requires its dedicated adapter")
        token = self.signer.sign(context, action, lease_id)
        prefix = "" if action in ("register", "revoke") else "lease/"
        try:
            response = await self.client.post(
                f"/internal/v1/sessions/{context.session_id}/{prefix}{action}",
                headers={"Authorization": "Bearer " + token},
                follow_redirects=False,
                timeout=10,
            )
        except httpx.TransportError:
            raise BrowserControlUncertain(
                "Browser response unavailable; reconcile before retry"
            ) from None
        if response.status_code in (401, 403):
            raise BrowserControlRejected("Browser command rejected")
        if response.status_code in (404, 409):
            raise BrowserControlConflict("Browser session state conflicts with command")
        if action in ("register", "revoke"):
            if response.status_code != 204:
                raise BrowserControlUncertain("Browser command result unconfirmed")
            return None
        if response.status_code != 200:
            raise BrowserControlUncertain("Browser command result unconfirmed")
        try:
            result = LeaseResponse.model_validate_json(response.content)
        except ValidationError:
            raise BrowserControlUncertain("Invalid browser command response") from None
        if (
            result.session_id != context.session_id
            or result.owner_id != context.owner_id
            or (lease_id is not None and result.lease_id != lease_id)
            or result.expires_at.utcoffset() is None
            or result.draining != (action == "stop")
            or (action != "stop" and result.expires_at <= datetime.now(UTC))
        ):
            raise BrowserControlUncertain("Browser response does not match command")
        return BrowserLease(
            result.session_id, result.lease_id, result.owner_id, result.expires_at, result.draining
        )

    async def lifecycle(
        self, context: BrowserControlContext, action: Literal["create", "release", "finish"]
    ) -> BrowserSession:
        token = self.signer.sign(context, action)
        try:
            response = await self.client.post(
                f"/internal/v1/sessions/{context.session_id}/lifecycle/{action}",
                headers={"Authorization": "Bearer " + token},
                follow_redirects=False,
                timeout=50,
            )
        except httpx.TransportError:
            raise BrowserControlUncertain("Browser lifecycle requires reconciliation") from None
        if response.status_code in (401, 403):
            raise BrowserControlRejected("Browser lifecycle rejected")
        if response.status_code in (404, 409):
            raise BrowserControlConflict("Browser lifecycle requires reconciliation")
        if response.status_code != 200:
            raise BrowserControlUncertain("Browser lifecycle result unconfirmed")
        try:
            result = SessionResponse.model_validate_json(response.content)
        except ValidationError:
            raise BrowserControlUncertain("Browser lifecycle response invalid") from None
        if result.session_id != context.session_id or result.status != (
            "live" if action == "create" else "released"
        ):
            raise BrowserControlUncertain("Browser lifecycle response does not match command")
        if action == "finish" and type(result.login_verified) is not bool:
            raise BrowserControlUncertain("Login verification evidence is missing")
        return BrowserSession(result.session_id, result.status, result.login_verified)
