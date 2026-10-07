from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from services.api.app.factory import create_app
from services.api.application.ports.browser_viewer import (
    BrowserViewerTicket,
    BrowserViewerTicketIssuer,
    BrowserViewerTicketRejected,
)
from services.api.infrastructure.browser_control import BrowserCommandSigner
from services.api.routes.browser_viewer import ViewerTicketResponse
from tests.api.test_browser_control import control_context
from tests.api.test_health import FakeAgentRuntime, build_settings, create_token, use_signing_key


def test_viewer_ticket_requires_authentication_and_configuration() -> None:
    with TestClient(create_app(build_settings(), lambda _settings: FakeAgentRuntime())) as client:
        session_id = uuid4()
        assert (
            client.post(f"/api/v1/browser/sessions/{session_id}/viewer-ticket").status_code == 401
        )


def test_viewer_ticket_is_short_lived_and_uses_signed_viewer_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    app = create_app(build_settings(), lambda _settings: FakeAgentRuntime())
    session_id = uuid4()
    command_key = Ed25519PrivateKey.generate()
    ticket = BrowserViewerTicket(
        session_id,
        BrowserCommandSigner(command_key).sign(
            replace(control_context(), session_id=session_id, user_id="user-123"), "viewer"
        ),
        datetime.now(UTC) + timedelta(seconds=60),
    )
    issuer = AsyncMock()
    issuer.issue.return_value = ticket
    app.state.browser_viewer_ticket_issuer = cast(BrowserViewerTicketIssuer, issuer)
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/browser/sessions/{session_id}/viewer-ticket",
            headers={"Authorization": "Bearer " + create_token(private_key)},
            json={},
        )

    assert response.status_code == 200
    payload = ViewerTicketResponse.model_validate(response.json())
    assert payload.session_id == session_id
    assert payload.token == ticket.token
    assert response.headers["cache-control"] == "no-store"
    issuer.issue.assert_awaited_once()
    actor, requested_session = issuer.issue.await_args.args
    assert actor.user_id == "user-123"
    assert requested_session == session_id
    signed = jwt.decode(
        payload.token,
        command_key.public_key(),
        algorithms=["EdDSA"],
        audience="careeract-browser",
    )
    assert signed["action"] == "viewer"


def test_viewer_ticket_rejection_does_not_expose_session_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    app = create_app(build_settings(), lambda _settings: FakeAgentRuntime())
    issuer = AsyncMock()
    issuer.issue.side_effect = BrowserViewerTicketRejected("internal session details")
    app.state.browser_viewer_ticket_issuer = cast(BrowserViewerTicketIssuer, issuer)
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/browser/sessions/{uuid4()}/viewer-ticket",
            headers={"Authorization": "Bearer " + create_token(private_key)},
            json={},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "browser_viewer_rejected"
    assert "internal session details" not in response.text
