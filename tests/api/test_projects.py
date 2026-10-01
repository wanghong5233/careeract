import asyncio
import base64
import importlib
import json
import os
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.app.factory import create_app
from services.api.application.context import ActorContext
from services.api.application.ports.projects import ProjectRepository
from services.api.application.projects import ProjectService
from services.api.domain.project import ProjectConflict, ProjectInvalid
from services.api.infrastructure.projects import PostgresProjectRepository
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


def test_projects_require_identity_and_reject_invalid_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    app = create_app(build_settings(), lambda _settings: FakeAgentRuntime())
    with TestClient(app) as client:
        assert client.get("/api/v1/projects").status_code == 401
        headers = {"Authorization": "Bearer " + token_for(private_key, "synthetic-user")}
        invalid = [
            {"purpose": "missing title"},
            {"title": " "},
            {"title": "Project", "status": "unknown"},
            {"title": "Project", "user_id": "someone-else"},
        ]
        for payload in invalid:
            response = client.post("/api/v1/projects", headers=headers, json=payload)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "invalid_project"
        for changes in ({}, {"title": None}, {"purpose": None}, {"status": None}):
            response = client.patch(
                f"/api/v1/projects/{uuid4()}",
                headers=headers,
                json={**changes, "version": str(uuid4())},
            )
            assert response.status_code == 422
        marker = "SYNTHETIC_PRIVATE_TEXT"
        response = client.post("/api/v1/projects", headers=headers, json={"title": marker * 50})
        assert response.status_code == 422
        assert marker not in response.text
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "payload",
    [
        [],
        None,
        {"updated_at": "2026-10-01", "id": str(UUID(int=1))},
        {"updated_at": "2026-10-01T00:00:00+00:00", "id": {}},
    ],
)
def test_invalid_project_cursor_is_sanitized(
    payload: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    cursor = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    app = create_app(build_settings(), lambda _settings: FakeAgentRuntime())
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + token_for(private_key, "synthetic-user")}
        for invalid in (cursor, "%", "A", "x" * 513):
            response = client.get("/api/v1/projects", params={"cursor": invalid}, headers=headers)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "invalid_project"
            assert "traceback" not in response.text.lower()


async def test_project_validation_precedes_storage() -> None:
    repository = AsyncMock()
    service = ProjectService(cast(ProjectRepository, repository))
    actor = ActorContext("synthetic-user", str(uuid4()))
    for title, purpose in ((" ", ""), ("Valid", "x" * 4001)):
        with pytest.raises(ProjectInvalid):
            await service.create(actor, title=title, purpose=purpose, status="planned")
    with pytest.raises(ProjectInvalid):
        await service.update(
            actor, uuid4(), title=" ", purpose=None, status=None, expected_version=uuid4()
        )
    with pytest.raises(ProjectInvalid):
        await service.update(
            actor, uuid4(), title=None, purpose=None, status=None, expected_version=uuid4()
        )
    repository.create.assert_not_called()
    repository.update.assert_not_called()


@pytest.mark.skipif(
    os.environ.get("RUN_PROJECT_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL project integration",
)
async def test_projects_isolate_persist_and_reject_stale_updates(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    settings = build_settings().model_copy(update={"database_url": PostgresDsn(database_url)})
    app = create_app(settings, lambda _settings: FakeAgentRuntime())
    service: ProjectService = app.state.project_service
    repository = service.repository
    assert isinstance(repository, PostgresProjectRepository)
    first_user, second_user = uuid4().hex, uuid4().hex
    try:
        async with repository.engine.begin() as connection:
            for user_id in (first_user, second_user):
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
            created = await client.post(
                "/api/v1/projects",
                headers=first_headers,
                json={"title": "求职阶段", "purpose": "完成校招闭环", "status": "active"},
            )
            assert created.status_code == 201
            project = created.json()
            project_id, version = project["id"], project["version"]
            assert (await client.get("/api/v1/projects", headers=first_headers)).json()["items"]
            assert (
                await client.get("/api/v1/projects/" + project_id, headers=second_headers)
            ).status_code == 404
            other_page = await client.get("/api/v1/projects", headers=second_headers)
            assert other_page.json()["items"] == []
            forbidden = await client.patch(
                "/api/v1/projects/" + project_id,
                headers=second_headers,
                json={"title": "Unauthorized", "version": version},
            )
            assert forbidden.status_code == 404
            raced = await asyncio.gather(
                *(
                    client.patch(
                        "/api/v1/projects/" + project_id,
                        headers=first_headers,
                        json={"purpose": f"完成真实投递闭环 {index}", "version": version},
                    )
                    for index in range(2)
                )
            )
            assert sorted(response.status_code for response in raced) == [200, 409]
            updated = next(response.json() for response in raced if response.status_code == 200)
            stale = await client.patch(
                "/api/v1/projects/" + project_id,
                headers=first_headers,
                json={"title": "旧版本", "version": version},
            )
            assert stale.status_code == 409
            assert stale.json()["error"]["code"] == "project_conflict"
            assert (
                await client.get("/api/v1/projects/" + project_id, headers=first_headers)
            ).json()["purpose"] == updated["purpose"]
            retry_id = str(uuid4())
            payload = {"id": retry_id, "title": "可重试项目", "purpose": "合成测试"}
            retries = await asyncio.gather(
                *(
                    client.post("/api/v1/projects", headers=first_headers, json=payload)
                    for _ in range(2)
                )
            )
            assert all(response.status_code == 201 for response in retries)
            assert retries[0].json() == retries[1].json()
            collision = await client.post("/api/v1/projects", headers=second_headers, json=payload)
            assert collision.status_code == 409
            assert "可重试项目" not in collision.text
            changed_retry = await client.post(
                "/api/v1/projects", headers=first_headers, json={**payload, "title": "新内容"}
            )
            assert changed_retry.status_code == 409
            archived = await client.patch(
                "/api/v1/projects/" + retry_id,
                headers=first_headers,
                json={"status": "archived", "version": retries[0].json()["version"]},
            )
            assert archived.status_code == 200
            current = await client.get(
                "/api/v1/projects", headers=first_headers, params={"archived": "false", "limit": 1}
            )
            assert current.json()["items"][0]["id"] == project_id
            archive = await client.get(
                "/api/v1/projects", headers=first_headers, params={"archived": "true"}
            )
            assert [item["id"] for item in archive.json()["items"]] == [retry_id]
        actor = ActorContext(first_user, str(uuid4()))
        created_projects = await asyncio.gather(
            *(
                service.create(actor, title=f"项目 {index}", purpose="", status="planned")
                for index in range(5)
            )
        )
        assert len(created_projects) == 5
        with pytest.raises(ProjectConflict):
            await service.update(
                actor,
                created_projects[0].id,
                title="冲突",
                purpose=None,
                status=None,
                expected_version=UUID(int=0),
            )
        visited: list[UUID] = []
        cursor = None
        while True:
            page = await service.list(actor, cursor=cursor, limit=2)
            visited.extend(project.id for project in page.items)
            cursor = page.next_cursor
            if cursor is None:
                break
        assert len(visited) == len(set(visited)) == 7
        assert {item.id for item in created_projects}.issubset(visited)
        expected = await service.read(actor, UUID(project_id))
    finally:
        await repository.engine.dispose()

    fresh_engine = create_async_engine(database_url)
    try:
        recovered = await ProjectService(PostgresProjectRepository(fresh_engine)).read(
            actor, UUID(project_id)
        )
        assert recovered == expected
    finally:
        await fresh_engine.dispose()


@pytest.mark.skipif(
    os.environ.get("RUN_PROJECT_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL migration compatibility",
)
async def test_legacy_project_migration_preserves_existing_rows(database_url: str) -> None:
    migration = importlib.import_module(
        "services.api.migrations.versions.0005_career_projects_legacy"
    )
    engine = create_async_engine(database_url)
    legacy_id = uuid4()
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("CREATE TABLE career.projects (project_id UUID PRIMARY KEY, summary TEXT)")
            )
            await connection.execute(
                text("INSERT INTO career.projects VALUES (:id, 'Synthetic legacy row')"),
                {"id": legacy_id},
            )

            def upgrade(sync: Connection) -> None:
                with Operations.context(MigrationContext.configure(sync)):
                    migration.upgrade()

            def downgrade(sync: Connection) -> None:
                with Operations.context(MigrationContext.configure(sync)):
                    migration.downgrade()

            await connection.run_sync(upgrade)
            assert (
                await connection.scalar(
                    text("SELECT summary FROM career.projects_legacy_0004 WHERE project_id=:id"),
                    {"id": legacy_id},
                )
                == "Synthetic legacy row"
            )
            await connection.run_sync(downgrade)
            assert (
                await connection.scalar(
                    text("SELECT summary FROM career.projects WHERE project_id=:id"),
                    {"id": legacy_id},
                )
                == "Synthetic legacy row"
            )
            await connection.run_sync(upgrade)
    finally:
        await engine.dispose()
