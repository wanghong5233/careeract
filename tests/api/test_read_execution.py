import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from unittest.mock import AsyncMock, call
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from services.api.app.factory import create_app
from services.api.application.context import ActorContext
from services.api.application.ports.boss_page import (
    BossConversationObservation,
    BossPageObservation,
)
from services.api.application.ports.browser_control import (
    BrowserControlConflict,
    BrowserControlContext,
    BrowserControlUncertain,
)
from services.api.application.ports.browser_viewer import BrowserViewerTicketRejected
from services.api.application.ports.read_execution import ReadExecutionRepository
from services.api.application.read_execution import ReadExecutionService
from services.api.domain.execution import (
    BossReadTarget,
    ExecutionConflict,
    ExecutionUnavailable,
    MaterialReadTarget,
    ReadExecution,
)
from services.api.infrastructure.browser_control import BrowserCommandSigner, BrowserControlClient
from services.api.infrastructure.browser_viewer import PostgresBrowserViewerTicketIssuer
from services.api.infrastructure.execution import PostgresExecutionRepository
from services.api.infrastructure.materials import PostgresMaterialRepository
from services.api.infrastructure.read_execution import PostgresReadExecutionRepository
from services.browser.app.factory import create_app as create_browser_app
from services.browser.sessions.authentication import CommandVerifier
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.sessions.steel import SteelSessionManager
from tests.api.test_execution_semantics import Scenario
from tests.api.test_execution_semantics import scenario as scenario
from tests.api.test_health import FakeAgentRuntime, build_settings, use_signing_key
from tests.api.test_projects import token_for
from tests.browser.test_postgres_leases import database_url as database_url
from tests.browser.test_steel_sessions import SyntheticSteel

integration = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL integration",
)


def test_read_api_requires_explicit_consent_and_restricts_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, key)
    app = create_app(build_settings(), lambda _settings: FakeAgentRuntime())
    repository = AsyncMock()
    app.state.read_execution_service = ReadExecutionService(
        cast(ReadExecutionRepository, repository)
    )
    headers = {
        "Authorization": "Bearer " + token_for(key, "synthetic-user"),
        "Idempotency-Key": str(uuid4()),
    }
    path = f"/api/v1/connections/boss/{uuid4()}/read"
    version = str(uuid4())
    with TestClient(app) as client:
        assert client.post(path, json={}).status_code == 401
        for body in (
            {"version": version},
            {"version": version, "authorize_read": False},
            {"version": version, "authorize_read": 1},
            {"version": version, "authorize_read": True, "scope": "boss.send"},
            {"version": version, "authorize_read": True, "user_id": "another-user"},
            {"version": version, "authorize_read": True, "browser_session_id": str(uuid4())},
        ):
            response = client.post(path, headers=headers, json=body)
            assert response.status_code == 422
            assert response.headers["Cache-Control"] == "no-store"
        repository.accept.assert_not_awaited()
        repository.accept.side_effect = ExecutionConflict("private resource diagnostics")
        response = client.post(
            path, headers=headers, json={"version": version, "authorize_read": True}
        )
        assert response.status_code == 409
        assert "private" not in response.text
        actor = repository.accept.call_args.args[0]
        assert actor.user_id == "synthetic-user"
        target = repository.accept.call_args.kwargs["target"]
        assert isinstance(target, BossReadTarget)
        assert target.connection_version == UUID(version)
        repository.read.return_value = None
        assert client.get(path + "/" + str(uuid4()), headers=headers).status_code == 404


@pytest.mark.asyncio
async def test_read_runner_reuses_lifecycle_and_reconciles_browser_cleanup() -> None:
    repository = AsyncMock()
    control = AsyncMock()
    page_reader = AsyncMock()
    actor = ActorContext(user_id="runner-user", request_id=str(uuid4()))
    context = BrowserControlContext(
        user_id=actor.user_id,
        session_id=uuid4(),
        task_id=uuid4(),
        authorization_id=uuid4(),
        authorization_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        attempt_id=uuid4(),
        request_id=uuid4(),
        owner_id="boss-read",
    )
    observation = BossPageObservation(
        url="https://www.zhipin.com/web/geek/chat",
        title="BOSS",
        kind="conversations",
        state="ready",
        jobs=(),
        signals=(),
        conversations=(),
        messages=(),
    )
    repository.reserve_browser.return_value = context
    page_reader.read_boss_page.return_value = observation
    result = await ReadExecutionService(repository).run_boss_read(
        actor, context.task_id, control=control, page_reader=page_reader
    )
    assert result == observation
    assert control.mock_calls == [
        call.send(context, "register"),
        call.lifecycle(context, "create"),
        call.send(context, "revoke"),
        call.lifecycle(context, "release"),
    ]
    repository.finish_browser.assert_awaited_once_with(
        actor, context.task_id, outcome="read_completed", observation=observation
    )

    repository.reset_mock()
    control.reset_mock()
    page_reader.reset_mock()
    repository.reserve_browser.return_value = context
    control.lifecycle.side_effect = [BrowserControlConflict("create rejected"), None]
    with pytest.raises(ExecutionUnavailable):
        await ReadExecutionService(repository).run_boss_read(
            actor, context.task_id, control=control, page_reader=page_reader
        )
    control.send.assert_any_await(context, "revoke")
    repository.finish_browser.assert_awaited_once_with(
        actor, context.task_id, outcome="read_failed", observation=None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_at", ["register", "create", "read", "revoke", "release", "bug", "cancel"]
)
async def test_read_runner_preserves_uncertainty_and_cleans_up(failure_at: str) -> None:
    repository, control, page_reader = AsyncMock(), AsyncMock(), AsyncMock()
    actor = ActorContext(user_id="runner-user", request_id=str(uuid4()))
    context = BrowserControlContext(
        actor.user_id,
        uuid4(),
        uuid4(),
        uuid4(),
        datetime.now(UTC) + timedelta(minutes=5),
        uuid4(),
        uuid4(),
        "boss-read",
    )
    repository.reserve_browser.return_value = context
    page_reader.read_boss_page.return_value = BossPageObservation(
        "https://www.zhipin.com/web/geek/chat", "BOSS", "conversations", "ready", (), (), (), ()
    )
    if failure_at == "register":
        control.send.side_effect = [BrowserControlUncertain(), None]
    elif failure_at == "create":
        control.lifecycle.side_effect = [BrowserControlUncertain(), None]
    elif failure_at == "read":
        page_reader.read_boss_page.side_effect = BrowserControlUncertain()
    elif failure_at == "revoke":
        control.send.side_effect = [None, BrowserControlUncertain()]
    elif failure_at == "release":
        control.lifecycle.side_effect = [None, BrowserControlUncertain()]
    elif failure_at == "bug":
        page_reader.read_boss_page.side_effect = ValueError("Programming error")
    else:
        page_reader.read_boss_page.side_effect = asyncio.CancelledError()
    expected = (
        ValueError
        if failure_at == "bug"
        else asyncio.CancelledError
        if failure_at == "cancel"
        else ExecutionUnavailable
    )
    with pytest.raises(expected):
        await ReadExecutionService(repository).run_boss_read(
            actor, context.task_id, control=control, page_reader=page_reader
        )
    control.send.assert_any_await(context, "revoke")
    if failure_at not in {"register", "revoke"}:
        assert control.mock_calls[-2:] == [
            call.send(context, "revoke"),
            call.lifecycle(context, "release"),
        ]
    repository.finish_browser.assert_awaited_once_with(
        actor,
        context.task_id,
        outcome="read_failed" if failure_at in {"read", "bug", "cancel"} else "read_unknown",
        observation=page_reader.read_boss_page.return_value
        if failure_at in {"revoke", "release"}
        else None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["needs_login", "risk", "unstable", "unknown"])
async def test_read_runner_does_not_complete_unusable_pages(
    state: Literal["needs_login", "risk", "unstable", "unknown"],
) -> None:
    repository, control, page_reader = AsyncMock(), AsyncMock(), AsyncMock()
    actor = ActorContext(user_id="runner-user", request_id=str(uuid4()))
    context = BrowserControlContext(
        actor.user_id,
        uuid4(),
        uuid4(),
        uuid4(),
        datetime.now(UTC) + timedelta(minutes=5),
        uuid4(),
        uuid4(),
        "boss-read",
    )
    repository.reserve_browser.return_value = context
    page_reader.read_boss_page.return_value = BossPageObservation(
        "https://www.zhipin.com/", "BOSS", "unknown", state, (), (), (), ()
    )
    with pytest.raises(ExecutionUnavailable):
        await ReadExecutionService(repository).run_boss_read(
            actor, context.task_id, control=control, page_reader=page_reader
        )
    repository.finish_browser.assert_awaited_once_with(
        actor,
        context.task_id,
        outcome="read_failed",
        observation=page_reader.read_boss_page.return_value,
    )


@integration
@pytest.mark.asyncio
async def test_read_tasks_keep_login_and_bind_owned_versioned_resources(scenario: Scenario) -> None:
    login = await scenario.accept()
    async with scenario.engine.begin() as database:
        connection_version = await database.scalar(
            text(
                "UPDATE career.boss_connections SET status='connected', "
                "browser_session_id=:session "
                "WHERE id=:id RETURNING version"
            ),
            {"id": scenario.connection_id, "session": uuid4()},
        )
    repository = PostgresReadExecutionRepository(scenario.engine)
    target = BossReadTarget(scenario.connection_id, connection_version)
    request_key = uuid4()

    async def accept() -> ReadExecution:
        return await repository.accept(
            scenario.actor,
            target=target,
            request_key=request_key,
            authorization_lifetime=timedelta(minutes=5),
        )

    accepted = await asyncio.gather(*(accept() for _counter in range(3)))
    assert all(item == accepted[0] for item in accepted)
    current = accepted[0]
    assert current.authorization.scope == "boss.read"
    assert current.task.connection_id is None and current.attempt.browser_session_id is None
    assert await repository.read(scenario.other, current.task.id) is None
    with pytest.raises(ExecutionConflict):
        await repository.cancel(scenario.other, current.task.id)
    await scenario.engine.dispose()
    assert await accept() == current
    old_login = await PostgresExecutionRepository(scenario.engine).read_login(
        scenario.actor, scenario.connection_id
    )
    assert old_login is not None and old_login.task == login[0]
    with pytest.raises(ExecutionConflict):
        await repository.accept(
            scenario.actor,
            target=target,
            request_key=login[0].request_key,
            authorization_lifetime=timedelta(minutes=5),
        )
    second = await repository.accept(
        replace(scenario.actor, request_id=str(uuid4())),
        target=target,
        request_key=uuid4(),
        authorization_lifetime=timedelta(minutes=5),
    )
    assert second.task.id != current.task.id
    with pytest.raises(ExecutionConflict):
        await repository.accept(
            scenario.actor,
            target=replace(target, connection_id=scenario.other_connection_id),
            request_key=uuid4(),
            authorization_lifetime=timedelta(minutes=5),
        )
    with pytest.raises(ExecutionConflict):
        await repository.accept(
            scenario.actor,
            target=replace(target, connection_version=uuid4()),
            request_key=uuid4(),
            authorization_lifetime=timedelta(minutes=5),
        )
    cancelled = await repository.cancel(scenario.actor, current.task.id)
    assert cancelled.task.status == "cancelled"
    assert cancelled.authorization.status == "revoked"
    assert cancelled.attempt.outcome == "cancelled_before_start"
    assert await accept() == cancelled
    assert await repository.cancel(scenario.actor, current.task.id) == cancelled
    with pytest.raises(ExecutionConflict):
        await repository.accept(
            scenario.actor,
            target=replace(target, connection_version=uuid4()),
            request_key=request_key,
            authorization_lifetime=timedelta(minutes=5),
        )


@integration
@pytest.mark.asyncio
async def test_material_read_has_no_browser_and_enforces_owner_and_versions(
    scenario: Scenario,
) -> None:
    materials = PostgresMaterialRepository(scenario.engine)
    material = await materials.create(
        scenario.actor,
        material_id=uuid4(),
        project_id=None,
        title="Synthetic result",
        body="Synthetic artifact content",
    )
    target = MaterialReadTarget(
        material.material.id, material.current_version.id, material.material.version
    )
    repository = PostgresReadExecutionRepository(scenario.engine)
    for invalid_target, actor in (
        (target, scenario.other),
        (replace(target, version_id=uuid4()), scenario.actor),
        (replace(target, material_version=uuid4()), scenario.actor),
    ):
        with pytest.raises(ExecutionConflict):
            await repository.accept(
                actor,
                target=invalid_target,
                request_key=uuid4(),
                authorization_lifetime=timedelta(minutes=5),
            )
    service = ReadExecutionService(repository)
    request_key = uuid4()
    accepted = await service.accept_material(
        scenario.actor,
        material_id=target.material_id,
        version_id=target.version_id,
        expected_version=target.material_version,
        request_key=request_key,
    )
    assert accepted.target == target and accepted.authorization.scope == "material.read"
    assert accepted.task.connection_id is None and accepted.attempt.browser_session_id is None
    with pytest.raises(IntegrityError):
        async with scenario.engine.begin() as database:
            await database.execute(
                text("DELETE FROM career.materials WHERE id=:id"),
                {"id": target.material_id},
            )
    assert await repository.read(scenario.actor, accepted.task.id) == accepted
    with pytest.raises(ExecutionConflict):
        await PostgresExecutionRepository(scenario.engine).bind_browser_session(
            scenario.actor, accepted.attempt.id, uuid4()
        )
    await materials.create_version(
        scenario.actor,
        material_id=target.material_id,
        base_version_id=target.version_id,
        body="Changed synthetic result",
        source="user",
    )
    restored = await repository.read(scenario.actor, accepted.task.id)
    assert restored == accepted
    latest_material = await materials.get(scenario.actor, target.material_id)
    assert latest_material is not None and latest_material.current_version.id != target.version_id
    with pytest.raises(ExecutionConflict):
        await service.accept_material(
            scenario.actor,
            material_id=target.material_id,
            version_id=target.version_id,
            expected_version=target.material_version,
            request_key=uuid4(),
        )
    assert (
        await service.accept_material(
            scenario.actor,
            material_id=target.material_id,
            version_id=target.version_id,
            expected_version=target.material_version,
            request_key=request_key,
        )
        == accepted
    )


@integration
@pytest.mark.asyncio
@pytest.mark.parametrize("minutes", [-1, 16])
async def test_read_authorization_deadline_is_bounded(scenario: Scenario, minutes: int) -> None:
    with pytest.raises(ExecutionConflict, match="expire"):
        await PostgresReadExecutionRepository(scenario.engine).accept(
            scenario.actor,
            target=BossReadTarget(scenario.connection_id, uuid4()),
            request_key=uuid4(),
            authorization_lifetime=timedelta(minutes=minutes),
        )


@integration
@pytest.mark.asyncio
async def test_read_http_accept_replay_read_cancel_and_owner_isolation(
    scenario: Scenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, key)
    async with scenario.engine.begin() as database:
        version = await database.scalar(
            text(
                "UPDATE career.boss_connections SET status='connected', "
                "browser_session_id=:session "
                "WHERE id=:id RETURNING version"
            ),
            {"id": scenario.connection_id, "session": uuid4()},
        )
    app = create_app(build_settings(), lambda _settings: FakeAgentRuntime())
    app.state.read_execution_service = ReadExecutionService(
        PostgresReadExecutionRepository(scenario.engine)
    )
    headers = {
        "Authorization": "Bearer " + token_for(key, scenario.actor.user_id),
        "Idempotency-Key": str(uuid4()),
    }
    path = f"/api/v1/connections/boss/{scenario.connection_id}/read"
    body = {"version": str(version), "authorize_read": True}
    async with httpx.AsyncClient(
        base_url="http://test", transport=httpx.ASGITransport(app=app)
    ) as client:
        missing_key = await client.post(
            path, headers={"Authorization": headers["Authorization"]}, json=body
        )
        assert missing_key.status_code == 422
        accepted = await client.post(path, headers=headers, json=body)
        assert accepted.status_code == 201
        assert accepted.headers["Cache-Control"] == "no-store"
        result = accepted.json()
        assert result["task_status"] == result["attempt_status"] == "accepted"
        assert result["scope"] == "boss.read" and result["browser_session_id"] is None
        assert (await client.post(path, headers=headers, json=body)).json() == result
        task_path = path + "/" + result["task_id"]
        assert (await client.get(task_path, headers=headers)).json() == result
        other_headers = {"Authorization": "Bearer " + token_for(key, scenario.other.user_id)}
        wrong_path = (
            f"/api/v1/connections/boss/{scenario.other_connection_id}/read/" + result["task_id"]
        )
        for inaccessible_path, request_headers in (
            (task_path, other_headers),
            (wrong_path, headers),
        ):
            for method in (client.get, client.delete):
                response = await method(inaccessible_path, headers=request_headers)
                assert response.status_code == 404
                assert response.json()["error"]["code"] == "execution_not_found"
                assert response.headers["Cache-Control"] == "no-store"
        assert (await client.get(task_path, headers=headers)).json() == result
        cancelled = await client.delete(task_path, headers=headers)
        assert cancelled.status_code == 200
        cancelled_result = cancelled.json()
        assert cancelled_result["task_status"] == "cancelled"
        assert cancelled_result["authorization_status"] == "revoked"
        assert (await client.delete(task_path, headers=headers)).json() == cancelled_result
        assert (await client.post(path, headers=headers, json=body)).json() == cancelled_result


@integration
@pytest.mark.asyncio
async def test_read_browser_reservation_rechecks_authorization_and_persists_outcome(
    scenario: Scenario,
) -> None:
    repository = PostgresReadExecutionRepository(scenario.engine)
    async with scenario.engine.begin() as database:
        version = await database.scalar(
            text(
                "UPDATE career.boss_connections SET status='connected', "
                "browser_session_id=:session WHERE id=:id RETURNING version"
            ),
            {"id": scenario.connection_id, "session": uuid4()},
        )
    service = ReadExecutionService(repository)
    accepted = await service.accept_boss(
        scenario.actor,
        connection_id=scenario.connection_id,
        expected_version=version,
        request_key=uuid4(),
    )
    context = await repository.reserve_browser(scenario.actor, accepted.task.id, uuid4())
    assert context.owner_id == "boss-read"
    running = await repository.read(scenario.actor, accepted.task.id)
    assert running is not None and running.task.status == "running"
    completed = await repository.finish_browser(
        scenario.actor, accepted.task.id, outcome="read_completed"
    )
    assert completed.task.status == "completed"
    assert completed.attempt.status == "completed"
    assert completed.attempt.outcome == "read_completed"
    assert (
        await repository.finish_browser(scenario.actor, accepted.task.id, outcome="read_completed")
        == completed
    )


@integration
@pytest.mark.asyncio
async def test_read_prototype_runs_once_and_restores_owned_results(
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, key)
    async with scenario.engine.begin() as database:
        version = await database.scalar(
            text(
                "UPDATE career.boss_connections SET status='connected', "
                "browser_session_id=:session "
                "WHERE id=:id RETURNING version"
            ),
            {"id": scenario.connection_id, "session": uuid4()},
        )
    repository = PostgresReadExecutionRepository(scenario.engine)
    app = create_app(build_settings(), lambda _settings: FakeAgentRuntime())
    app.state.read_execution_service = ReadExecutionService(repository)
    control, reader = AsyncMock(), AsyncMock()
    observation = BossPageObservation(
        "https://www.zhipin.com/web/geek/chat",
        "Synthetic communication",
        "conversations",
        "ready",
        (),
        (),
        (
            BossConversationObservation(
                "synthetic-conversation",
                "Synthetic recruiter",
                None,
                None,
                "Synthetic message",
                True,
                None,
            ),
        ),
        (),
    )
    reader.read_boss_page.return_value = observation
    app.state.browser_control, app.state.boss_page_reader = control, reader
    headers = {
        "Authorization": "Bearer " + token_for(key, scenario.actor.user_id),
        "Idempotency-Key": str(uuid4()),
    }
    path = f"/api/v1/connections/boss/{scenario.connection_id}/read"
    async with httpx.AsyncClient(
        base_url="http://test", transport=httpx.ASGITransport(app=app)
    ) as client:
        assert (await client.get(path, headers=headers)).json() is None
        accepted = await client.post(
            path, headers=headers, json={"version": str(version), "authorize_read": True}
        )
        assert accepted.status_code == 201
        task_id = accepted.json()["task_id"]
        task_path = path + "/" + task_id
        assert (await client.get(task_path + "/result", headers=headers)).json() is None
        other_headers = {"Authorization": "Bearer " + token_for(key, scenario.other.user_id)}
        assert (
            await client.post(task_path + "/run", headers=other_headers, json={})
        ).status_code == 404
        assert (
            await client.post(task_path + "/run", headers=headers, json={"owner_id": "viewer"})
        ).status_code == 422
        control.send.assert_not_awaited()
        completed = await client.post(task_path + "/run", headers=headers, json={})
        assert completed.status_code == 200 and completed.json()["task_status"] == "completed"
        restored = await client.get(task_path + "/result", headers=headers)
        assert restored.status_code == 200 and restored.headers["Cache-Control"] == "no-store"
        assert (
            restored.json()["page"]["conversations"][0]["conversation_id"]
            == "synthetic-conversation"
        )
        assert (await client.get(task_path + "/result", headers=other_headers)).status_code == 404
        assert (await client.post(task_path + "/run", headers=headers, json={})).status_code == 409
        reader.read_boss_page.assert_awaited_once()
        assert (await client.get(path, headers=headers)).json() == completed.json()
    await scenario.engine.dispose()
    result = await ReadExecutionService(repository).boss_result(
        scenario.actor, scenario.connection_id, UUID(task_id)
    )
    assert result is not None and result.page == observation
    assert await repository.read_page_result(scenario.other, UUID(task_id)) is None


@integration
@pytest.mark.asyncio
async def test_read_task_viewer_is_owned_read_only_and_ends_with_execution(
    scenario: Scenario,
) -> None:
    async with scenario.engine.begin() as database:
        version = await database.scalar(
            text(
                "UPDATE career.boss_connections SET status='connected', "
                "browser_session_id=:session "
                "WHERE id=:id RETURNING version"
            ),
            {"id": scenario.connection_id, "session": uuid4()},
        )
    repository = PostgresReadExecutionRepository(scenario.engine)
    accepted = await ReadExecutionService(repository).accept_boss(
        scenario.actor,
        connection_id=scenario.connection_id,
        expected_version=version,
        request_key=uuid4(),
    )
    context = await repository.reserve_browser(scenario.actor, accepted.task.id, uuid4())
    key, steel = Ed25519PrivateKey.generate(), SyntheticSteel()
    issuer = PostgresBrowserViewerTicketIssuer(scenario.engine, BrowserCommandSigner(key))
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as steel_client:
        browser = create_browser_app(
            verifier=CommandVerifier(key.public_key()),
            store=PostgresLeaseStore(scenario.engine),
            steel_sessions=SteelSessionManager(steel_client, scenario.engine),
        )
        async with httpx.AsyncClient(
            base_url="http://browser", transport=httpx.ASGITransport(app=browser)
        ) as client:
            control = BrowserControlClient(client, BrowserCommandSigner(key))
            await control.send(context, "register")
            with pytest.raises(BrowserViewerTicketRejected):
                await issuer.issue(scenario.actor, context.session_id, mode="watch")
            await control.lifecycle(context, "create")
            assert (
                await issuer.issue(scenario.actor, context.session_id, mode="watch")
            ).mode == "watch"
            for actor, mode in ((scenario.other, "watch"), (scenario.actor, "control")):
                with pytest.raises(BrowserViewerTicketRejected):
                    await issuer.issue(
                        actor, context.session_id, mode=cast(Literal["watch", "control"], mode)
                    )
            await control.send(context, "revoke")
            await control.lifecycle(context, "release")
            await repository.finish_browser(
                scenario.actor, accepted.task.id, outcome="read_completed"
            )
            with pytest.raises(BrowserViewerTicketRejected):
                await issuer.issue(scenario.actor, context.session_id, mode="watch")


@integration
@pytest.mark.asyncio
async def test_unknown_read_requires_owned_release_before_reconciliation(
    scenario: Scenario,
) -> None:
    async with scenario.engine.begin() as database:
        version = await database.scalar(
            text(
                "UPDATE career.boss_connections SET status='connected', "
                "browser_session_id=:session "
                "WHERE id=:id RETURNING version"
            ),
            {"id": scenario.connection_id, "session": uuid4()},
        )
    repository = PostgresReadExecutionRepository(scenario.engine)
    service = ReadExecutionService(repository)
    accepted = await service.accept_boss(
        scenario.actor,
        connection_id=scenario.connection_id,
        expected_version=version,
        request_key=uuid4(),
    )
    context = await repository.reserve_browser(scenario.actor, accepted.task.id, uuid4())
    key, steel = Ed25519PrivateKey.generate(), SyntheticSteel()
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as steel_client:
        browser = create_browser_app(
            verifier=CommandVerifier(key.public_key()),
            store=PostgresLeaseStore(scenario.engine),
            steel_sessions=SteelSessionManager(steel_client, scenario.engine),
        )
        async with httpx.AsyncClient(
            base_url="http://browser", transport=httpx.ASGITransport(app=browser)
        ) as client:
            control = BrowserControlClient(client, BrowserCommandSigner(key))
            await control.send(context, "register")
            await control.lifecycle(context, "create")
            unknown = await repository.finish_browser(
                scenario.actor, accepted.task.id, outcome="read_unknown"
            )
            with pytest.raises(ExecutionConflict):
                await repository.reconcile_released(scenario.other, accepted.task.id)
            with pytest.raises(ExecutionConflict):
                await repository.reconcile_released(scenario.actor, accepted.task.id)
            await control.send(context, "revoke")
            with pytest.raises(ExecutionConflict):
                await repository.reconcile_released(scenario.actor, accepted.task.id)
            await control.lifecycle(context, "release")
            failed = await service.reconcile_boss(
                scenario.actor, scenario.connection_id, accepted.task.id
            )
            assert failed.task.status == "failed" and failed.attempt.outcome == "read_failed"
            assert failed.attempt.finished_at == unknown.attempt.finished_at
            assert failed.authorization.status == "revoked"
            assert await repository.reconcile_released(scenario.actor, accepted.task.id) == failed
            with pytest.raises(ExecutionConflict):
                await repository.reserve_browser(scenario.actor, accepted.task.id, uuid4())


@integration
@pytest.mark.asyncio
@pytest.mark.parametrize("registered", [False, True])
async def test_unknown_read_without_creation_is_revoked_before_reconciliation(
    scenario: Scenario, registered: bool
) -> None:
    async with scenario.engine.begin() as database:
        version = await database.scalar(
            text(
                "UPDATE career.boss_connections SET status='connected', "
                "browser_session_id=:session WHERE id=:id RETURNING version"
            ),
            {"id": scenario.connection_id, "session": uuid4()},
        )
    repository = PostgresReadExecutionRepository(scenario.engine)
    service = ReadExecutionService(repository)
    accepted = await service.accept_boss(
        scenario.actor,
        connection_id=scenario.connection_id,
        expected_version=version,
        request_key=uuid4(),
    )
    context = await repository.reserve_browser(scenario.actor, accepted.task.id, uuid4())
    key, steel = Ed25519PrivateKey.generate(), SyntheticSteel()
    original_sessions = [session.copy() for session in steel.sessions]
    async with httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(steel.respond)
    ) as steel_client:
        browser = create_browser_app(
            verifier=CommandVerifier(key.public_key()),
            store=PostgresLeaseStore(scenario.engine),
            steel_sessions=SteelSessionManager(steel_client, scenario.engine),
        )
        async with httpx.AsyncClient(
            base_url="http://browser", transport=httpx.ASGITransport(app=browser)
        ) as client:
            control = BrowserControlClient(client, BrowserCommandSigner(key))
            if registered:
                await control.send(context, "register")
            unknown = await repository.finish_browser(
                scenario.actor, accepted.task.id, outcome="read_unknown"
            )
            with pytest.raises(ExecutionConflict):
                await repository.reconcile_released(scenario.actor, accepted.task.id)
            failed = await service.reconcile_boss(
                scenario.actor, scenario.connection_id, accepted.task.id, control=control
            )
            assert failed.task.status == "failed"
            assert failed.authorization.status == "revoked"
            assert failed.attempt.finished_at == unknown.attempt.finished_at
            assert failed.attempt.browser_session_id == context.session_id
            assert steel.sessions == original_sessions
            assert steel.writes == []
