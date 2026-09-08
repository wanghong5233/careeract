from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jwt import PyJWKClient, PyJWKClientConnectionError
from pydantic import AnyHttpUrl, PostgresDsn, SecretStr

from services.api.app.factory import create_app
from services.api.app.settings import Settings
from services.api.infrastructure.agent_runtime import build_agent_os


class FakeAgentRuntime:
    def __init__(self) -> None:
        self.app = FastAPI()

    def get_app(self) -> FastAPI:
        return self.app


def build_settings() -> Settings:
    return Settings(
        database_url=PostgresDsn(
            "postgresql+asyncpg://careeract:careeract@localhost:15432/careeract"
        ),
        agno_database_url=PostgresDsn(
            "postgresql+psycopg://careeract:careeract@localhost:15432/careeract"
        ),
        auth_jwks_url=AnyHttpUrl("http://localhost:3000/api/auth/jwks"),
        auth_issuer="http://localhost:3000",
        auth_audience="http://localhost:3000",
        litellm_master_key=SecretStr("test-key"),
    )


def build_app() -> FastAPI:
    app = create_app(build_settings(), lambda _settings: FakeAgentRuntime())

    @app.get("/api/whoami")
    async def whoami(request: Request) -> dict[str, str]:
        return {"user_id": request.state.user_id}

    return app


def test_health_is_public() -> None:
    with TestClient(build_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_agent_stream_requires_authentication() -> None:
    with TestClient(build_app()) as client:
        response = client.post("/agui", json={})

    assert response.status_code == 401


def test_agentos_management_routes_are_not_public() -> None:
    with TestClient(build_app()) as client:
        response = client.get("/agents")

    assert response.status_code == 404


def create_token(
    private_key: Ed25519PrivateKey,
    *,
    issuer: str = "http://localhost:3000",
    audience: str = "http://localhost:3000",
    expires_at: datetime | None = None,
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": "user-123",
            "email": "user@example.com",
            "iss": issuer,
            "aud": audience,
            "iat": now,
            "exp": expires_at or now + timedelta(minutes=15),
        },
        private_key,
        algorithm="EdDSA",
        headers={"kid": "test-key"},
    )


def use_signing_key(
    monkeypatch: pytest.MonkeyPatch,
    private_key: Ed25519PrivateKey,
) -> None:
    def get_signing_key(
        _client: PyJWKClient,
        _token: str,
    ) -> SimpleNamespace:
        return SimpleNamespace(key=private_key.public_key())

    monkeypatch.setattr(PyJWKClient, "get_signing_key_from_jwt", get_signing_key)


def test_valid_jwt_sets_trusted_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)

    with TestClient(build_app()) as client:
        response = client.get(
            "/api/whoami",
            headers={"Authorization": f"Bearer {create_token(private_key)}"},
        )

    assert response.status_code == 200
    assert response.json() == {"user_id": "user-123"}


@pytest.mark.parametrize(
    ("issuer", "audience", "expires_at"),
    [
        ("https://attacker.example", "http://localhost:3000", None),
        ("http://localhost:3000", "https://other-service.example", None),
        (
            "http://localhost:3000",
            "http://localhost:3000",
            datetime.now(UTC) - timedelta(minutes=1),
        ),
    ],
)
def test_untrusted_jwt_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    issuer: str,
    audience: str,
    expires_at: datetime | None,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    token = create_token(
        private_key,
        issuer=issuer,
        audience=audience,
        expires_at=expires_at,
    )

    with TestClient(build_app()) as client:
        response = client.get(
            "/api/whoami",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401


def test_jwks_outage_is_not_reported_as_invalid_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()

    def fail_to_fetch_key(
        _client: PyJWKClient,
        _token: str,
    ) -> None:
        raise PyJWKClientConnectionError("JWKS unavailable")

    monkeypatch.setattr(PyJWKClient, "get_signing_key_from_jwt", fail_to_fetch_key)

    with TestClient(build_app()) as client:
        response = client.get(
            "/api/whoami",
            headers={"Authorization": f"Bearer {create_token(private_key)}"},
        )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


def test_agent_runtime_uses_private_schema_and_disables_telemetry() -> None:
    runtime = build_agent_os(build_settings())

    assert runtime.db is not None
    assert runtime.db.db_schema == "agno"
    assert runtime.telemetry is False
    assert runtime.agents is not None
    assert all(agent.telemetry is False for agent in runtime.agents)
