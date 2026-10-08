import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from services.api.application.browser_registration import BrowserRegistrationService
from services.api.application.context import ActorContext
from services.api.application.ports.browser_viewer import BrowserViewerTicketRejected
from services.api.domain.execution import (
    ExecutionAttempt,
    ExecutionAuthorization,
    ExecutionConflict,
    ExecutionTask,
    ExecutionUnavailable,
)
from services.api.infrastructure.boss_connections import PostgresBossConnectionRepository
from services.api.infrastructure.browser_control import BrowserCommandSigner, BrowserControlClient
from services.api.infrastructure.browser_viewer import PostgresBrowserViewerTicketIssuer
from services.api.infrastructure.execution import PostgresExecutionRepository
from services.browser.app.factory import create_app
from services.browser.sessions.authentication import CommandRejected, CommandVerifier
from services.browser.sessions.postgres import PostgresLeaseStore
from tests.browser.test_postgres_leases import database_url as database_url

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL integration",
)


@dataclass
class Scenario:
    engine: AsyncEngine
    actor: ActorContext
    other: ActorContext
    connection_id: UUID
    other_connection_id: UUID

    async def accept(self) -> tuple[ExecutionTask, ExecutionAuthorization, ExecutionAttempt]:
        return await PostgresExecutionRepository(self.engine).accept(
            self.actor,
            connection_id=self.connection_id,
            kind="boss_login",
            request_key=uuid4(),
            scope="boss.login",
            authorization_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            request_id=uuid4(),
        )


@pytest.fixture
async def scenario(database_url: str) -> AsyncIterator[Scenario]:
    engine = create_async_engine(database_url, hide_parameters=True)
    users = ["execution-test-" + uuid4().hex for _ in range(2)]
    try:
        async with engine.begin() as database:
            for user_id in users:
                await database.execute(
                    text(
                        'INSERT INTO auth."user" (id,name,email,"emailVerified") '
                        "VALUES (:id,'Synthetic',:email,false)"
                    ),
                    {"id": user_id, "email": user_id + "@example.invalid"},
                )
        actors = [ActorContext(user_id, str(uuid4())) for user_id in users]
        connections = [
            await PostgresBossConnectionRepository(engine).start(
                actor, connection_id=uuid4(), request_key=uuid4()
            )
            for actor in actors
        ]
        yield Scenario(engine, actors[0], actors[1], connections[0].id, connections[1].id)
    finally:
        async with engine.begin() as database:
            await database.execute(
                text(
                    "DELETE FROM browser.commands WHERE session_id IN "
                    "(SELECT session_id FROM browser.sessions WHERE user_id IN (:first,:second))"
                ),
                {"first": users[0], "second": users[1]},
            )
            await database.execute(
                text("DELETE FROM browser.sessions WHERE user_id IN (:first,:second)"),
                {"first": users[0], "second": users[1]},
            )
            await database.execute(
                text('DELETE FROM auth."user" WHERE id IN (:first,:second)'),
                {"first": users[0], "second": users[1]},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_accept_is_idempotent_concurrent_and_does_not_extend_authorization(
    scenario: Scenario,
) -> None:
    repository = PostgresExecutionRepository(scenario.engine)
    request_key = uuid4()

    async def accept() -> tuple[ExecutionTask, ExecutionAuthorization, ExecutionAttempt]:
        return await repository.accept(
            scenario.actor,
            connection_id=scenario.connection_id,
            kind="boss_login",
            request_key=request_key,
            scope="boss.login",
            authorization_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            request_id=uuid4(),
        )

    accepted = await asyncio.gather(*(accept() for _ in range(4)))
    assert all(item == accepted[0] for item in accepted)
    task, authorization, attempt = accepted[0]
    assert len({task.id, authorization.id, attempt.id, scenario.connection_id}) == 4
    assert task.connection_id == scenario.connection_id
    assert attempt.task_id == task.id and attempt.authorization_id == authorization.id
    await scenario.engine.dispose()
    assert await accept() == accepted[0]
    with pytest.raises(ExecutionConflict):
        await repository.accept(
            scenario.actor,
            connection_id=scenario.other_connection_id,
            kind="boss_login",
            request_key=request_key,
            scope="boss.login",
            authorization_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            request_id=uuid4(),
        )
    with pytest.raises(ExecutionConflict):
        await scenario.accept()


@pytest.mark.asyncio
async def test_binding_is_owned_and_only_one_caller_can_start(scenario: Scenario) -> None:
    repository = PostgresExecutionRepository(scenario.engine)
    task, authorization, attempt = await scenario.accept()
    assert await repository.read_attempt(scenario.other, attempt.id) is None
    with pytest.raises(ExecutionConflict):
        await repository.bind_browser_session(scenario.other, attempt.id, uuid4())
    bindings = await asyncio.gather(
        *(repository.bind_browser_session(scenario.actor, attempt.id, uuid4()) for _ in range(2)),
        return_exceptions=True,
    )
    assert sum(isinstance(item, ExecutionConflict) for item in bindings) == 1
    context = next(item for item in bindings if not isinstance(item, BaseException))
    assert context.task_id == task.id and context.authorization_id == authorization.id
    assert context.attempt_id == attempt.id and context.request_id == attempt.request_id
    current = await repository.read_attempt(scenario.actor, attempt.id)
    assert current is not None and current.status == "running"
    assert current.browser_session_id == context.session_id
    async with scenario.engine.connect() as database:
        assert (
            await database.scalar(
                text("SELECT status FROM career.execution_tasks WHERE id=:id"), {"id": task.id}
            )
            == "running"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["expired", "revoked", "cancelled"])
async def test_inactive_authorization_or_task_cannot_start(scenario: Scenario, state: str) -> None:
    repository = PostgresExecutionRepository(scenario.engine)
    task, authorization, attempt = await scenario.accept()
    if state == "revoked":
        cancelled = await repository.revoke(scenario.actor, attempt.id)
        assert cancelled.status == "cancelled" and cancelled.outcome == "cancelled_before_start"
        assert await repository.revoke(scenario.actor, attempt.id) == cancelled
    else:
        async with scenario.engine.begin() as database:
            if state == "expired":
                await database.execute(
                    text(
                        "UPDATE career.execution_authorizations SET expires_at=clock_timestamp() "
                        "WHERE id=:id"
                    ),
                    {"id": authorization.id},
                )
            else:
                await database.execute(
                    text("UPDATE career.execution_tasks SET status='cancelled' WHERE id=:id"),
                    {"id": task.id},
                )
    with pytest.raises(ExecutionConflict):
        await repository.bind_browser_session(scenario.actor, attempt.id, uuid4())


@pytest.mark.asyncio
async def test_registration_uses_real_semantics_and_viewer_ticket_checks_authorization(
    scenario: Scenario,
) -> None:
    repository = PostgresExecutionRepository(scenario.engine)
    task, authorization, attempt = await scenario.accept()
    private_key = Ed25519PrivateKey.generate()
    signer = BrowserCommandSigner(private_key)
    app = create_app(
        verifier=CommandVerifier(private_key.public_key()),
        store=PostgresLeaseStore(scenario.engine),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://browser"
    ) as client:
        service = BrowserRegistrationService(repository, BrowserControlClient(client, signer))
        registered = await service.register(scenario.actor, attempt.id)
        assert registered.status == "waiting" and registered.outcome == "browser_registered"
        assert registered.browser_session_id is not None
        issuer = PostgresBrowserViewerTicketIssuer(scenario.engine, signer)
        ticket = await issuer.issue(scenario.actor, registered.browser_session_id)
        claims = jwt.decode(
            ticket.token,
            private_key.public_key(),
            algorithms=["EdDSA"],
            audience="careeract-browser",
        )
        assert claims["task_id"] == str(task.id)
        assert claims["authorization_id"] == str(authorization.id)
        assert claims["attempt_id"] == str(attempt.id)
        viewer_command = CommandVerifier(private_key.public_key()).verify(
            ticket.token, registered.browser_session_id, "viewer"
        )
        store = PostgresLeaseStore(scenario.engine)
        viewer_lease = await store.acquire_viewer(viewer_command)
        with pytest.raises(BrowserViewerTicketRejected):
            await issuer.issue(scenario.other, registered.browser_session_id)
        revoked = await service.revoke(scenario.actor, attempt.id)
        assert revoked.status == "unknown" and revoked.outcome == "cleanup_required"
        with pytest.raises(BrowserViewerTicketRejected):
            await issuer.issue(scenario.actor, registered.browser_session_id)
        async with scenario.engine.connect() as database:
            assert await database.scalar(
                text("SELECT revoked FROM browser.sessions WHERE session_id=:id"),
                {"id": registered.browser_session_id},
            )
            assert (
                await database.scalar(
                    text("SELECT lease_id FROM browser.sessions WHERE session_id=:id"),
                    {"id": registered.browser_session_id},
                )
                == viewer_lease.lease_id
            )
        with pytest.raises(CommandRejected):
            await store.check_viewer(viewer_command, viewer_lease.lease_id)


@pytest.mark.asyncio
async def test_lost_response_records_unknown_and_reconstruction_never_resends(
    scenario: Scenario,
) -> None:
    repository = PostgresExecutionRepository(scenario.engine)
    _, _, attempt = await scenario.accept()
    private_key = Ed25519PrivateKey.generate()
    verifier = CommandVerifier(private_key.public_key())
    store = PostgresLeaseStore(scenario.engine)
    calls = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        token = request.headers["authorization"].removeprefix("Bearer ")
        session_id = UUID(request.url.path.split("/")[-2])
        await store.manage(verifier.verify(token, session_id, "register"))
        raise httpx.ReadTimeout("synthetic private diagnostic", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://browser"
    ) as client:
        service = BrowserRegistrationService(
            repository, BrowserControlClient(client, BrowserCommandSigner(private_key))
        )
        with pytest.raises(ExecutionUnavailable):
            await service.register(scenario.actor, attempt.id)
        current = await repository.read_attempt(scenario.actor, attempt.id)
        assert current is not None and current.status == "unknown"
        assert current.outcome == "registration_unconfirmed"
        assert current.browser_session_id is not None
        with pytest.raises(BrowserViewerTicketRejected):
            await PostgresBrowserViewerTicketIssuer(
                scenario.engine, BrowserCommandSigner(private_key)
            ).issue(scenario.actor, current.browser_session_id)
        await scenario.engine.dispose()
        restored = BrowserRegistrationService(
            PostgresExecutionRepository(scenario.engine), service.control
        )
        with pytest.raises(ExecutionConflict):
            await restored.register(scenario.actor, attempt.id)
        assert calls == 1
        async with scenario.engine.connect() as database:
            assert (
                await database.scalar(
                    text("SELECT count(*) FROM browser.sessions WHERE session_id=:id"),
                    {"id": current.browser_session_id},
                )
                == 1
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid", ["scope", "long_expiry", "past_expiry", "other_connection", "attached_connection"]
)
async def test_accept_refuses_invalid_scope_deadline_or_connection(
    scenario: Scenario, invalid: str
) -> None:
    deadline = datetime.now(UTC) + timedelta(minutes=5)
    if invalid == "long_expiry":
        deadline += timedelta(hours=1)
    if invalid == "past_expiry":
        deadline -= timedelta(hours=1)
    if invalid == "attached_connection":
        async with scenario.engine.begin() as database:
            await database.execute(
                text("UPDATE career.boss_connections SET browser_session_id=:session WHERE id=:id"),
                {"id": scenario.connection_id, "session": uuid4()},
            )
    with pytest.raises(ExecutionConflict):
        await PostgresExecutionRepository(scenario.engine).accept(
            scenario.actor,
            connection_id=(
                scenario.other_connection_id
                if invalid == "other_connection"
                else scenario.connection_id
            ),
            kind="boss_login",
            request_key=uuid4(),
            scope="boss.send" if invalid == "scope" else "boss.login",
            authorization_expires_at=deadline,
            request_id=uuid4(),
        )
    async with scenario.engine.connect() as database:
        assert (
            await database.scalar(
                text("SELECT count(*) FROM career.execution_tasks WHERE user_id=:user_id"),
                {"user_id": scenario.actor.user_id},
            )
            == 0
        )


@pytest.mark.asyncio
async def test_cancellation_leaves_reserved_attempt_and_cannot_repeat(scenario: Scenario) -> None:
    repository = PostgresExecutionRepository(scenario.engine)
    _, _, attempt = await scenario.accept()
    entered = asyncio.Event()
    calls = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        entered.set()
        await asyncio.Event().wait()
        return httpx.Response(204)

    async with httpx.AsyncClient(
        base_url="http://browser", transport=httpx.MockTransport(respond)
    ) as client:
        service = BrowserRegistrationService(
            repository,
            BrowserControlClient(client, BrowserCommandSigner(Ed25519PrivateKey.generate())),
        )
        pending = asyncio.create_task(service.register(scenario.actor, attempt.id))
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
        finally:
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        current = await repository.read_attempt(scenario.actor, attempt.id)
        assert current is not None and current.status == "running"
        with pytest.raises(ExecutionConflict):
            await service.register(scenario.actor, attempt.id)
        assert calls == 1


@pytest.mark.asyncio
async def test_registration_rejection_records_failure_without_replay(scenario: Scenario) -> None:
    repository = PostgresExecutionRepository(scenario.engine)
    _, _, attempt = await scenario.accept()
    calls = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(403)

    async with httpx.AsyncClient(
        base_url="http://browser", transport=httpx.MockTransport(respond)
    ) as client:
        service = BrowserRegistrationService(
            repository,
            BrowserControlClient(client, BrowserCommandSigner(Ed25519PrivateKey.generate())),
        )
        rejected = await service.register(scenario.actor, attempt.id)
        assert rejected.status == "failed" and rejected.outcome == "registration_rejected"
        with pytest.raises(ExecutionConflict):
            await service.register(scenario.actor, attempt.id)
        assert calls == 1


@pytest.mark.asyncio
async def test_viewer_ticket_cannot_outlive_login_authorization_or_use_unbound_ids(
    scenario: Scenario,
) -> None:
    repository = PostgresExecutionRepository(scenario.engine)
    _, authorization, attempt = await scenario.accept()
    key = Ed25519PrivateKey.generate()
    signer = BrowserCommandSigner(key)
    issuer = PostgresBrowserViewerTicketIssuer(scenario.engine, signer)
    store = PostgresLeaseStore(scenario.engine)
    legacy_session = uuid4()
    await store.register(legacy_session, scenario.actor.user_id, uuid4(), uuid4())
    with pytest.raises(BrowserViewerTicketRejected):
        await issuer.issue(scenario.actor, legacy_session)
    app = create_app(verifier=CommandVerifier(key.public_key()), store=store)
    async with httpx.AsyncClient(
        base_url="http://browser", transport=httpx.ASGITransport(app=app)
    ) as client:
        registered = await BrowserRegistrationService(
            repository, BrowserControlClient(client, signer)
        ).register(scenario.actor, attempt.id)
    assert registered.browser_session_id is not None
    async with scenario.engine.begin() as database:
        deadline = await database.scalar(text("SELECT clock_timestamp() + interval '20 seconds'"))
        await database.execute(
            text("UPDATE career.execution_authorizations SET expires_at=:expires WHERE id=:id"),
            {"id": authorization.id, "expires": deadline},
        )
    ticket = await issuer.issue(scenario.actor, registered.browser_session_id)
    assert ticket.expires_at <= deadline
    claims = jwt.decode(
        ticket.token, key.public_key(), algorithms=["EdDSA"], audience="careeract-browser"
    )
    assert claims["exp"] <= deadline.timestamp()
    async with scenario.engine.begin() as database:
        await database.execute(
            text(
                "UPDATE career.execution_authorizations SET expires_at=clock_timestamp() "
                "WHERE id=:id"
            ),
            {"id": authorization.id},
        )
    with pytest.raises(BrowserViewerTicketRejected):
        await issuer.issue(scenario.actor, registered.browser_session_id)
