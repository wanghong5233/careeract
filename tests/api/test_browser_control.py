from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from services.api.application.ports.browser_control import (
    BrowserControlContext,
    BrowserControlRejected,
    BrowserControlUncertain,
)
from services.api.infrastructure.browser_control import BrowserCommandSigner, BrowserControlClient


def control_context() -> BrowserControlContext:
    return BrowserControlContext(
        user_id="synthetic-user",
        session_id=uuid4(),
        task_id=uuid4(),
        authorization_id=uuid4(),
        authorization_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        attempt_id=uuid4(),
        request_id=uuid4(),
        owner_id="synthetic-executor",
    )


def test_signer_caps_lifetime_and_allows_expired_authorization_cleanup() -> None:
    key = Ed25519PrivateKey.generate()
    signer = BrowserCommandSigner(key)
    context = replace(
        control_context(), authorization_expires_at=datetime.now(UTC) + timedelta(seconds=15)
    )
    token = signer.sign(context, "acquire")
    payload = jwt.decode(
        token, key.public_key(), algorithms=["EdDSA"], audience="careeract-browser"
    )
    assert payload["exp"] == int(context.authorization_expires_at.timestamp())
    assert payload["exp"] - payload["iat"] <= 60
    expired = replace(context, authorization_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(BrowserControlRejected):
        signer.sign(expired, "register")
    assert signer.sign(expired, "revoke")
    with pytest.raises(BrowserControlRejected):
        signer.sign(context, "renew")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "redirect", "server", "invalid", "wrong-session"])
async def test_unconfirmed_results_are_not_retried_or_exposed(failure: str) -> None:
    context = control_context()
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if failure == "timeout":
            raise httpx.ReadTimeout("untrusted diagnostic text", request=request)
        if failure == "redirect":
            return httpx.Response(307, headers={"Location": "http://untrusted.invalid"})
        if failure == "server":
            return httpx.Response(503, text="untrusted diagnostic text")
        if failure == "invalid":
            return httpx.Response(200, text="untrusted diagnostic text")
        return httpx.Response(
            200,
            json={
                "session_id": str(uuid4()),
                "lease_id": str(uuid4()),
                "owner_id": context.owner_id,
                "expires_at": context.authorization_expires_at.isoformat(),
                "draining": False,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://browser"
    ) as client:
        adapter = BrowserControlClient(client, BrowserCommandSigner(Ed25519PrivateKey.generate()))
        with pytest.raises(BrowserControlUncertain) as failure_info:
            await adapter.send(context, "acquire")
        assert "untrusted" not in str(failure_info.value)
        assert calls == 1


@pytest.mark.parametrize("action", ["create", "release"])
@pytest.mark.parametrize(
    "failure", ["timeout", "redirect", "server", "invalid", "wrong-session", "wrong-state"]
)
async def test_lifecycle_unconfirmed_response_never_retries(
    action: Literal["create", "release"], failure: str
) -> None:
    context = control_context()
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path.endswith("/lifecycle/" + action)
        if failure == "timeout":
            raise httpx.ReadTimeout("private browser diagnostics", request=request)
        if failure == "redirect":
            return httpx.Response(307, headers={"Location": "http://untrusted.invalid"})
        if failure == "server":
            return httpx.Response(503, text="private browser diagnostics")
        if failure == "invalid":
            return httpx.Response(200, text="private browser diagnostics")
        return httpx.Response(
            200,
            json={
                "session_id": str(uuid4() if failure == "wrong-session" else context.session_id),
                "status": ("live" if action == "create" else "released")
                if failure != "wrong-state"
                else ("released" if action == "create" else "live"),
            },
        )

    async with httpx.AsyncClient(
        base_url="http://browser", transport=httpx.MockTransport(respond)
    ) as client:
        adapter = BrowserControlClient(client, BrowserCommandSigner(Ed25519PrivateKey.generate()))
        with pytest.raises(BrowserControlUncertain) as result:
            await adapter.lifecycle(context, action)
        assert calls == 1 and "private" not in str(result.value)
