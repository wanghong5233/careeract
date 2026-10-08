from datetime import UTC, datetime
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from services.browser.app.factory import create_app
from services.browser.sessions.authentication import (
    BrowserCommand,
    CommandRejected,
    CommandVerifier,
)


def command_payload() -> dict[str, object]:
    now = int(datetime.now(UTC).timestamp())
    return {
        "iss": "careeract-api",
        "aud": "careeract-browser",
        "sub": "synthetic-user",
        "iat": now,
        "exp": now + 60,
        "jti": str(uuid4()),
        "session_id": str(uuid4()),
        "task_id": str(uuid4()),
        "authorization_id": str(uuid4()),
        "attempt_id": str(uuid4()),
        "request_id": str(uuid4()),
        "owner_id": "executor-1",
        "action": "acquire",
    }


def test_valid_signed_command_and_wrong_scope() -> None:
    from uuid import UUID

    private_key = Ed25519PrivateKey.generate()
    verifier = CommandVerifier(private_key.public_key())
    payload = command_payload()
    token = jwt.encode(payload, private_key, algorithm="EdDSA")
    session_id = UUID(str(payload["session_id"]))
    assert verifier.verify(token, session_id, "acquire").sub == "synthetic-user"
    with pytest.raises(CommandRejected):
        verifier.verify(token, uuid4(), "acquire")
    with pytest.raises(CommandRejected):
        verifier.verify(token, session_id, "stop")


def test_small_issue_time_skew_is_bounded_and_does_not_extend_expiration() -> None:
    private_key = Ed25519PrivateKey.generate()
    payload = command_payload()
    now = int(datetime.now(UTC).timestamp())
    payload.update(iat=now + 1, exp=now + 60)
    command = BrowserCommand.model_validate(payload)
    verifier = CommandVerifier(private_key.public_key())
    assert (
        verifier.verify(
            jwt.encode(payload, private_key, algorithm="EdDSA"), command.session_id, "acquire"
        )
        == command
    )
    assert command.is_current(now)
    assert not command.is_current(now - 2)
    assert not command.is_current(now + 60)
    payload.update(iat=now + 10)
    with pytest.raises(CommandRejected):
        verifier.verify(
            jwt.encode(payload, private_key, algorithm="EdDSA"), command.session_id, "acquire"
        )


@pytest.mark.parametrize(
    "change",
    [
        {"aud": "careeract-web"},
        {"iss": "untrusted"},
        {"sub": ""},
        {"exp": 1},
        {"exp": 9999999999},
        {"iat": 9999999999},
        {"task_id": "invalid"},
        {"iat": "1"},
        {"action": "release"},
        {"lease_id": str(uuid4())},
        {"writer_stopped": True},
    ],
)
def test_reject_invalid_signed_claims(change: dict[str, object]) -> None:
    from uuid import UUID

    private_key = Ed25519PrivateKey.generate()
    payload = command_payload() | change
    token = jwt.encode(payload, private_key, algorithm="EdDSA")
    with pytest.raises(CommandRejected):
        CommandVerifier(private_key.public_key()).verify(
            token, UUID(str(payload["session_id"])), "acquire"
        )


def test_reject_other_signer_and_missing_required_claim() -> None:
    from uuid import UUID

    private_key = Ed25519PrivateKey.generate()
    verifier = CommandVerifier(private_key.public_key())
    payload = command_payload()
    session_id = UUID(str(payload["session_id"]))
    token = jwt.encode(payload, Ed25519PrivateKey.generate(), algorithm="EdDSA")
    with pytest.raises(CommandRejected):
        verifier.verify(token, session_id, "acquire")
    del payload["authorization_id"]
    with pytest.raises(CommandRejected):
        verifier.verify(jwt.encode(payload, private_key, algorithm="EdDSA"), session_id, "acquire")


def test_control_disabled_by_default_and_no_release_route() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        assert client.post(f"/internal/v1/sessions/{uuid4()}/lease/acquire").status_code == 503
        assert client.post(f"/internal/v1/sessions/{uuid4()}/lease/release").status_code == 422


def test_unsigned_malformed_and_oversized_tokens_are_rejected() -> None:
    from uuid import UUID

    key = Ed25519PrivateKey.generate()
    payload = command_payload()
    verifier = CommandVerifier(key.public_key())
    for token in ["invalid", "x" * 8193, jwt.encode(payload, "", algorithm="none")]:
        with pytest.raises(CommandRejected):
            verifier.verify(token, UUID(str(payload["session_id"])), "acquire")
