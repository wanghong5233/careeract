from typing import Literal
from uuid import UUID

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, ValidationError

LeaseAction = Literal["acquire", "renew", "stop", "check"]
SessionAction = Literal["register", "revoke"]
Action = Literal["acquire", "renew", "stop", "check", "register", "revoke"]


class CommandRejected(Exception):
    pass


class BrowserCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    iss: Literal["careeract-api"]
    aud: Literal["careeract-browser"]
    sub: str = Field(min_length=1, max_length=256)
    iat: int = Field(strict=True)
    exp: int = Field(strict=True)
    jti: UUID
    session_id: UUID
    task_id: UUID
    authorization_id: UUID
    attempt_id: UUID
    request_id: UUID
    owner_id: str = Field(min_length=1, max_length=256)
    action: Action
    lease_id: UUID | None = None


class CommandVerifier:
    def __init__(self, public_key: Ed25519PublicKey) -> None:
        self.public_key = public_key

    def verify(self, token: str, session_id: UUID, action: Action) -> BrowserCommand:
        if len(token) > 8192:
            raise CommandRejected("Invalid browser command")
        try:
            payload = jwt.decode(
                token,
                self.public_key,
                algorithms=["EdDSA"],
                issuer="careeract-api",
                audience="careeract-browser",
                options={"require": ["iss", "aud", "sub", "iat", "exp", "jti"]},
            )
            command = BrowserCommand.model_validate(payload)
        except (jwt.InvalidTokenError, ValidationError, ValueError):
            raise CommandRejected("Invalid browser command") from None
        if (
            not 0 < command.exp - command.iat <= 60
            or command.session_id != session_id
            or command.action != action
            or (action in ("acquire", "register", "revoke")) != (command.lease_id is None)
        ):
            raise CommandRejected("Invalid browser command scope")
        return command
