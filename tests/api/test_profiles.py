import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.app.factory import create_app
from services.api.application.context import ActorContext
from services.api.application.profiles import ProfileService
from services.api.domain.profile import ProfileConflict, ProfileContent, ProfileEntry
from services.api.infrastructure.profiles import PostgresProfileRepository
from tests.api.test_health import FakeAgentRuntime, build_settings, use_signing_key
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


def test_profile_requires_identity_and_does_not_echo_invalid_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    app = create_app(build_settings(), lambda _settings: FakeAgentRuntime())
    with TestClient(app) as client:
        assert client.get("/api/v1/profile").status_code == 401
        assert client.put("/api/v1/profile", json={}).status_code == 401
        headers = {"Authorization": "Bearer " + token_for(private_key, "synthetic-user")}
        invalid = [
            {"content": {}, "version": None, "confirmed": False},
            {"content": {}, "version": None, "confirmed": 1},
            {"content": {}, "version": None, "confirmed": True, "user_id": "someone-else"},
            {"content": {"education": [{"title": " "}]}, "version": None, "confirmed": True},
            {"content": {"skills": "PRIVATE-SYNTHETIC" * 300}, "version": None, "confirmed": True},
            {"content": {}, "confirmed": True},
            {
                "content": {"projects": [{"title": "Project"}] * 31},
                "version": None,
                "confirmed": True,
            },
        ]
        for payload in invalid:
            response = client.put("/api/v1/profile", headers=headers, json=payload)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "invalid_profile"
            assert UUID(response.json()["error"]["request_id"])
            assert "PRIVATE-SYNTHETIC" not in response.text


def test_profile_domain_rejects_unusable_facts() -> None:
    with pytest.raises(ValueError):
        ProfileEntry(title="  ")
    with pytest.raises(ValueError):
        ProfileContent(goals="X" * 4001)
    with pytest.raises(ValueError):
        ProfileContent(education=(ProfileEntry(title="Degree"),) * 31)


@pytest.mark.skipif(
    os.environ.get("RUN_PROFILE_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL profile integration",
)
async def test_profile_isolation_persistence_and_concurrent_writes(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    settings = build_settings().model_copy(update={"database_url": PostgresDsn(database_url)})
    app = create_app(settings, lambda _settings: FakeAgentRuntime())
    service: ProfileService = app.state.profile_service
    repository = service.repository
    assert isinstance(repository, PostgresProfileRepository)
    first_user, second_user, race_user = (uuid4().hex for _ in range(3))
    try:
        async with repository.engine.begin() as connection:
            for user_id in (first_user, second_user, race_user):
                await connection.execute(
                    text(
                        'INSERT INTO auth."user" (id, name, email, "emailVerified") '
                        "VALUES (:user_id, 'Synthetic', :email, false)"
                    ),
                    {"user_id": user_id, "email": user_id + "@example.invalid"},
                )
        first_headers = {"Authorization": "Bearer " + token_for(private_key, first_user)}
        second_headers = {"Authorization": "Bearer " + token_for(private_key, second_user)}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            empty = await client.get("/api/v1/profile", headers=first_headers)
            assert empty.status_code == 200
            assert empty.json()["version"] is None
            assert empty.headers["cache-control"] == "no-store"
            content = {
                "display_name": "虚构测试用户",
                "education": [{"title": "计算机硕士", "organization": "测试大学"}],
                "projects": [{"title": "测试项目", "details": "合成内容", "evidence": "报告"}],
                "skills": "Python",
                "goals": "后端开发",
                "constraints": "测试城市",
            }
            saved = await client.put(
                "/api/v1/profile",
                headers=first_headers,
                json={"content": content, "version": None, "confirmed": True},
            )
            assert saved.status_code == 200
            first_version = saved.json()["version"]
            assert saved.json()["confirmed_at"]
            assert "user_id" not in saved.json()
            assert (
                await client.get("/api/v1/profile", headers=first_headers)
            ).json() == saved.json()
            other = await client.get(
                "/api/v1/profile?user_id=" + first_user, headers=second_headers
            )
            assert other.json()["version"] is None
            forbidden_update = await client.put(
                "/api/v1/profile",
                headers=second_headers,
                json={
                    "content": {"skills": "attacker"},
                    "version": first_version,
                    "confirmed": True,
                },
            )
            assert forbidden_update.status_code == 409
            assert (
                await client.get("/api/v1/profile", headers=first_headers)
            ).json() == saved.json()
            updated_content = content | {"goals": "平台工程"}
            candidates = await asyncio.gather(
                *(
                    client.put(
                        "/api/v1/profile",
                        headers=first_headers,
                        json={
                            "content": updated_content,
                            "version": first_version,
                            "confirmed": True,
                        },
                    )
                    for _ in range(2)
                )
            )
            assert sorted(response.status_code for response in candidates) == [200, 409]
            latest = (await client.get("/api/v1/profile", headers=first_headers)).json()
            assert latest["content"]["goals"] == "平台工程"
            assert latest["version"] != first_version
            stale_create = await client.put(
                "/api/v1/profile",
                headers=first_headers,
                json={"content": content, "version": None, "confirmed": True},
            )
            assert stale_create.status_code == 409
            second_saved = await client.put(
                "/api/v1/profile",
                headers=second_headers,
                json={"content": {"skills": "SQL"}, "version": None, "confirmed": True},
            )
            assert second_saved.status_code == 200
            assert (await client.get("/api/v1/profile", headers=first_headers)).json() == latest
        actor = ActorContext(user_id=race_user, request_id=str(uuid4()))
        outcomes = await asyncio.gather(
            *(
                service.confirm(actor, ProfileContent(skills="Race"), None, confirmed=True)
                for _ in range(2)
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(result, ProfileConflict) for result in outcomes) == 1
        with pytest.raises(ValueError):
            await service.confirm(actor, ProfileContent(), None, confirmed=False)
        await repository.engine.dispose()
        fresh_engine = create_async_engine(database_url)
        try:
            restored = await PostgresProfileRepository(fresh_engine).get(
                ActorContext(first_user, str(uuid4()))
            )
            assert restored is not None
            assert restored.content.goals == "平台工程"
            assert str(restored.version) == latest["version"]
        finally:
            await fresh_engine.dispose()
    finally:
        await repository.engine.dispose()
