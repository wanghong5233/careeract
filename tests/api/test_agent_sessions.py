import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.app.factory import create_app
from tests.api.test_health import build_settings, use_signing_key
from tests.browser.test_postgres_leases import database_url as database_url


def token_for(private_key: Ed25519PrivateKey, user_id: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user_id,
            "iss": "http://localhost:3000",
            "aud": "http://localhost:3000",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="EdDSA",
        headers={"kid": "test-key"},
    )


@dataclass
class SyntheticMessage:
    id: str
    role: str
    content: str
    created_at: int

    def get_content_string(self) -> str:
        return self.content


class SyntheticSession:
    def get_messages(self, **_: Any) -> list[SyntheticMessage]:
        return [
            SyntheticMessage("user-message", "user", "合成目标", 1),
            SyntheticMessage("assistant-message", "assistant", "合成建议", 2),
        ]


class SyntheticAgent:
    async def aget_session(self, *, session_id: str, user_id: str) -> SyntheticSession | None:
        if session_id == "opaque-test-session" and user_id == "first-user":
            return SyntheticSession()
        return None


class RuntimeWithHistory:
    def __init__(self) -> None:
        self.app = FastAPI()
        self.agents = [type("Agent", (), {"id": "careeract-agent"})()]
        self.agents[0] = SyntheticAgent()
        self.agents[0].id = "careeract-agent"

    def get_app(self) -> FastAPI:
        return self.app


@pytest.mark.skipif(
    os.environ.get("RUN_PROJECT_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL agent session integration",
)
@pytest.mark.asyncio
async def test_agent_session_history_is_user_scoped(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    settings = build_settings().model_copy(update={"database_url": PostgresDsn(database_url)})
    app = create_app(settings, lambda _settings: RuntimeWithHistory())
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            for user_id in ("first-user", "second-user"):
                await connection.execute(
                    text(
                        'INSERT INTO auth."user" (id, name, email, "emailVerified") '
                        "VALUES (:user_id, 'Synthetic', :email, false)"
                    ),
                    {"user_id": user_id, "email": user_id + "@example.invalid"},
                )
        first_headers = {"Authorization": "Bearer " + token_for(private_key, "first-user")}
        second_headers = {"Authorization": "Bearer " + token_for(private_key, "second-user")}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            associated = await client.put(
                "/api/v1/agent/session",
                headers=first_headers,
                json={"session_id": "opaque-test-session"},
            )
            assert associated.status_code == 200
            history = await client.get(
                "/api/v1/agent/session/history",
                headers=first_headers,
                params={"session_id": "opaque-test-session"},
            )
            assert history.status_code == 200
            assert [item["content"] for item in history.json()["messages"]] == [
                "合成目标",
                "合成建议",
            ]
            forbidden = await client.get(
                "/api/v1/agent/session/history",
                headers=second_headers,
                params={"session_id": "opaque-test-session"},
            )
            assert forbidden.status_code == 404
            assert "合成" not in forbidden.text
    finally:
        await engine.dispose()
