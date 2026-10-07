import asyncio
import importlib
import os
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.app.factory import create_app
from services.api.application.boss_connections import BossConnectionService
from services.api.application.context import ActorContext
from services.api.application.ports.boss_connections import BossConnectionRepository
from services.api.domain.boss_connection import (
    BossConnection,
    BossConnectionConflict,
    BossConnectionNotFound,
)
from services.api.infrastructure.boss_connections import PostgresBossConnectionRepository
from tests.api.test_health import FakeAgentRuntime, build_settings, use_signing_key
from tests.api.test_projects import token_for
from tests.browser.test_postgres_leases import database_url as database_url


def test_connection_api_authentication_validation_and_safe_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    app = create_app(build_settings(), lambda _settings: FakeAgentRuntime())
    repository = AsyncMock()
    app.state.boss_connection_service = BossConnectionService(
        cast(BossConnectionRepository, repository)
    )
    now, request_key = datetime.now(UTC), uuid4()
    connection = BossConnection(
        uuid4(),
        "first-user",
        "boss",
        request_key,
        uuid4(),
        None,
        "pending",
        None,
        "browser_session_not_started",
        now,
        now,
    )
    repository.start.return_value = connection
    repository.get_current.return_value = None
    repository.revoke.return_value = replace(connection, status="revoked")
    headers = {"Authorization": "Bearer " + token_for(private_key, "first-user")}
    with TestClient(app) as client:
        assert client.get("/api/v1/connections/boss").status_code == 401
        assert client.post("/api/v1/connections/boss", json={}).status_code == 401
        assert client.get("/api/v1/connections/boss", headers=headers).json() is None
        for payload, extra_headers in (
            ({}, {}),
            ({}, {"Idempotency-Key": "invalid"}),
            ({"user_id": "other"}, {"Idempotency-Key": str(request_key)}),
            ({"status": "connected"}, {"Idempotency-Key": str(request_key)}),
            ({"browser_session_id": str(uuid4())}, {"Idempotency-Key": str(request_key)}),
        ):
            response = client.post(
                "/api/v1/connections/boss", headers=headers | extra_headers, json=payload
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "invalid_boss_connection"
        repository.start.assert_not_awaited()
        created = client.post(
            "/api/v1/connections/boss",
            headers=headers | {"Idempotency-Key": str(request_key)},
            json={},
        )
        assert created.status_code == 201
        assert created.json()["status"] == "pending"
        assert created.json()["browser_session_id"] is None
        assert "user_id" not in created.json() and "request_key" not in created.json()
        assert created.headers["cache-control"] == "no-store"
        actor = repository.start.await_args.args[0]
        assert actor.user_id == "first-user"
        assert repository.start.await_args.kwargs["request_key"] == request_key
        for payload in ({}, {"version": str(connection.version), "user_id": "other"}):
            assert (
                client.request(
                    "DELETE",
                    f"/api/v1/connections/boss/{connection.id}",
                    headers=headers,
                    json=payload,
                ).status_code
                == 422
            )
        revoked = client.request(
            "DELETE",
            f"/api/v1/connections/boss/{connection.id}",
            headers=headers,
            json={"version": str(connection.version)},
        )
        assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
        repository.revoke.return_value = None
        assert (
            client.request(
                "DELETE",
                f"/api/v1/connections/boss/{uuid4()}",
                headers=headers,
                json={"version": str(uuid4())},
            ).status_code
            == 404
        )


async def test_revoke_absent_connection_is_not_found() -> None:
    repository = AsyncMock()
    repository.revoke.return_value = None
    service = BossConnectionService(cast(BossConnectionRepository, repository))
    with pytest.raises(BossConnectionNotFound):
        await service.revoke(
            ActorContext("synthetic", str(uuid4())), uuid4(), expected_version=uuid4()
        )


@pytest.mark.skipif(
    os.environ.get("RUN_BOSS_CONNECTION_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated Docker PostgreSQL integration",
)
async def test_connection_persistence_concurrency_replay_and_isolation(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(database_url, hide_parameters=True)
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    first_user, second_user = "boss-test-" + uuid4().hex, "boss-test-" + uuid4().hex
    first = ActorContext(first_user, str(uuid4()))
    second = ActorContext(second_user, str(uuid4()))
    service = BossConnectionService(PostgresBossConnectionRepository(engine))
    settings = build_settings().model_copy(update={"database_url": PostgresDsn(database_url)})
    app = create_app(settings, lambda _settings: FakeAgentRuntime())
    app.state.boss_connection_service = service
    try:
        async with engine.begin() as database:
            for user_id in (first_user, second_user):
                await database.execute(
                    text(
                        'INSERT INTO auth."user" (id,name,email,"emailVerified") '
                        "VALUES (:id,'Synthetic',:email,false)"
                    ),
                    {"id": user_id, "email": user_id + "@example.invalid"},
                )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"Authorization": "Bearer " + token_for(private_key, first_user)}
            shared_key = str(uuid4())
            candidates = await asyncio.gather(
                *(
                    client.post(
                        "/api/v1/connections/boss",
                        json={},
                        headers=headers | {"Idempotency-Key": shared_key},
                    )
                    for _ in range(4)
                )
            )
            assert all(response.status_code == 201 for response in candidates)
            assert len({response.json()["id"] for response in candidates}) == 1
        current = await service.read(first)
        assert current is not None and current.status == "pending"
        assert await service.read(second) is None
        assert (
            await service.repository.revoke(second, current.id, expected_version=current.version)
            is None
        )
        with pytest.raises(BossConnectionConflict):
            await service.revoke(first, current.id, expected_version=uuid4())
        replay = await service.start(first, request_key=current.request_key)
        assert replay == current
        with pytest.raises(BossConnectionConflict):
            await service.start(first, request_key=uuid4())
        revoked = await service.revoke(first, current.id, expected_version=current.version)
        assert revoked.status == "revoked" and revoked.version != current.version
        assert await service.start(first, request_key=current.request_key) == revoked
        next_connection = await service.start(first, request_key=uuid4())
        assert next_connection.id != current.id
        await service.revoke(first, current.id, expected_version=current.version)
        restored = BossConnectionService(PostgresBossConnectionRepository(engine))
        assert await restored.read(first) == next_connection
        other = await service.start(second, request_key=current.request_key)
        assert other.id != current.id
        async with engine.begin() as database:
            await database.execute(
                text("UPDATE career.boss_connections SET browser_session_id=:session WHERE id=:id"),
                {"id": next_connection.id, "session": uuid4()},
            )
        with pytest.raises(BossConnectionConflict):
            await service.revoke(
                first, next_connection.id, expected_version=next_connection.version
            )
    finally:
        async with engine.begin() as database:
            await database.execute(
                text('DELETE FROM auth."user" WHERE id IN (:first,:second)'),
                {"first": first_user, "second": second_user},
            )
        await engine.dispose()


@pytest.mark.skipif(
    os.environ.get("RUN_BOSS_CONNECTION_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated Docker PostgreSQL migration",
)
async def test_connection_migration_down_and_up(database_url: str) -> None:
    engine = create_async_engine(database_url, hide_parameters=True)
    migration = importlib.import_module("services.api.migrations.versions.0017_boss_connections")

    def roundtrip(database: Connection) -> None:
        with Operations.context(MigrationContext.configure(database)):
            migration.downgrade()
            assert database.scalar(text("SELECT to_regclass('career.boss_connections')")) is None
            migration.upgrade()
            assert (
                database.scalar(text("SELECT to_regclass('career.boss_connections')")) is not None
            )

    try:
        async with engine.begin() as database:
            await database.run_sync(roundtrip)
    finally:
        await engine.dispose()
