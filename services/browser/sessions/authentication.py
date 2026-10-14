from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, ValidationError

LeaseAction = Literal["acquire", "renew", "stop", "check"]
SessionAction = Literal["register", "revoke", "block_viewer"]
LifecycleAction = Literal["create", "release", "finish", "forget"]
Action = Literal[
    "acquire",
    "renew",
    "stop",
    "check",
    "register",
    "revoke",
    "block_viewer",
    "viewer",
    "watcher",
    "create",
    "release",
    "finish",
    "forget",
    "snapshot",
    "conversation",
    "observe_conversation",
    "send_message",
]


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
    conversation_id: str | None = Field(
        default=None, min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$"
    )
    message_id: str | None = Field(default=None, min_length=1, max_length=200)
    text_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    def is_current(self, timestamp: float) -> bool:
        return self.iat - 2 <= timestamp < self.exp and 0 < self.exp - self.iat <= 60


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
                options={
                    "require": ["iss", "aud", "sub", "iat", "exp", "jti"],
                    "verify_iat": False,
                },
            )
            command = BrowserCommand.model_validate(payload)
        except (jwt.InvalidTokenError, ValidationError, ValueError):
            raise CommandRejected("Invalid browser command") from None
        if (
            not command.is_current(datetime.now(UTC).timestamp())
            or command.session_id != session_id
            or command.action != action
            or (
                action
                in (
                    "acquire",
                    "register",
                    "revoke",
                    "block_viewer",
                    "viewer",
                    "watcher",
                    "create",
                    "release",
                    "finish",
                    "forget",
                    "snapshot",
                    "conversation",
                    "observe_conversation",
                    "send_message",
                )
            )
            != (command.lease_id is None)
            or (action in {"conversation", "observe_conversation", "send_message"})
            != (command.conversation_id is not None)
            or any(
                (value is not None) != (action == "send_message")
                for value in (command.message_id, command.text_digest, command.source_digest)
            )
        ):
            raise CommandRejected("Invalid browser command scope")
        return command
