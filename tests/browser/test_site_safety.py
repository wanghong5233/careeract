import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from pydantic import AnyHttpUrl
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from services.browser.sessions.authentication import BrowserCommand, CommandRejected
from services.browser.sessions.context import SiteScope
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.sessions.site_safety import (
    PostgresSiteSafetyStore,
    RiskReason,
    SiteRiskDetected,
    SiteSafetyBlocked,
)
from services.browser.site_adapters.boss_login import BossLoginNavigator, BossLoginUnavailable
from services.browser.site_adapters.boss_profile import BOSS_SCOPE
from tests.browser.test_command_authentication import command_payload
from tests.browser.test_postgres_leases import database_url as database_url
from tests.browser.test_postgres_leases import pytestmark as pytestmark


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["denied", "challenge", "rate_limited", "abnormal"])
async def test_risk_survives_new_task_store_and_lease_cleanup(
    database_url: str, reason: RiskReason
) -> None:
    engine = create_async_engine(database_url)
    command = BrowserCommand.model_validate(command_payload() | {"sub": "safety-" + uuid4().hex})
    leases = PostgresLeaseStore(engine)
    safety = PostgresSiteSafetyStore(engine, BOSS_SCOPE)
    try:
        await leases.register(
            command.session_id, command.sub, command.task_id, command.authorization_id
        )
        lease = await leases.execute(command)
        check = command.model_copy(update={"action": "check", "lease_id": lease.lease_id})
        with pytest.raises(SiteRiskDetected):
            async with (
                asyncio.timeout(5),
                leases.executor_action_guard(check),
                safety.action_guard(command.session_id, command.sub),
            ):
                raise SiteRiskDetected(reason)
        await leases.revoke(command.session_id)
        await leases.confirm_stopped(command.session_id, lease.lease_id)
        # Cleanup retains both the stop and the originating task/session evidence.
        replacement = command.model_copy(
            update={
                "session_id": uuid4(),
                "task_id": uuid4(),
                "authorization_id": uuid4(),
                "jti": uuid4(),
            }
        )
        await leases.register(
            replacement.session_id,
            replacement.sub,
            replacement.task_id,
            replacement.authorization_id,
        )
        await engine.dispose()
        restarted = create_async_engine(database_url)
        try:
            with pytest.raises(SiteSafetyBlocked):
                async with PostgresSiteSafetyStore(restarted, BOSS_SCOPE).action_guard(
                    replacement.session_id, replacement.sub
                ):
                    pytest.fail("A new process/task must not reach browser I/O")
            async with restarted.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM browser.site_safety "
                                "WHERE user_id=:user AND site='boss'"
                            ),
                            {"user": command.sub},
                        )
                    )
                    .mappings()
                    .one()
                )
                assert (
                    row["blocked"]
                    and row["session_id"] == command.session_id
                    and row["reason"] == reason
                )
        finally:
            await restarted.dispose()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_login_guard_persists_detection_and_blocks_new_navigation(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(database_url)
    user = "safety-" + uuid4().hex
    safety = PostgresSiteSafetyStore(engine, BOSS_SCOPE)
    leases = PostgresLeaseStore(engine)
    sessions = (uuid4(), uuid4())
    try:
        for session in sessions:
            await leases.register(session, user, uuid4(), uuid4())
        navigate = AsyncMock(side_effect=SiteRiskDetected("denied"))
        async with httpx.AsyncClient(base_url="http://synthetic.invalid") as client:
            navigator = BossLoginNavigator(
                client, AnyHttpUrl("http://synthetic.invalid"), risk_guard=safety.action_guard
            )
            monkeypatch.setattr(navigator, "_navigate", navigate)
            with pytest.raises(BossLoginUnavailable):
                await navigator(sessions[0])
            navigate.assert_awaited_once()
            navigate.reset_mock()
            with pytest.raises(BossLoginUnavailable):
                await navigator(sessions[1])
            navigate.assert_not_awaited()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_session_stop_serializes_actions_and_keeps_first_evidence(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    user = "safety-" + uuid4().hex
    first, second = uuid4(), uuid4()
    leases = PostgresLeaseStore(engine)
    safety = PostgresSiteSafetyStore(engine, BOSS_SCOPE)
    try:
        for session in (first, second):
            await leases.register(session, user, uuid4(), uuid4())
        async with safety.action_guard(first, user):
            stopping = asyncio.create_task(safety.record_stop(second, "challenge"))
            await asyncio.sleep(0.05)
            assert not stopping.done()
        await stopping
        await safety.record_stop(first, "denied")
        with pytest.raises(SiteSafetyBlocked):
            async with safety.action_guard(first, user):
                pytest.fail("Risk stop must fence the next action")
        async with engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM browser.site_safety WHERE user_id=:user AND site='boss'"
                        ),
                        {"user": user},
                    )
                )
                .mappings()
                .one()
            )
            assert row["session_id"] == second and row["reason"] == "challenge"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_site_and_user_isolation_and_wrong_session_ownership(database_url: str) -> None:
    engine = create_async_engine(database_url)
    user = "safety-" + uuid4().hex
    other = "other-" + uuid4().hex
    first, second = uuid4(), uuid4()
    leases = PostgresLeaseStore(engine)
    safety = PostgresSiteSafetyStore(engine, BOSS_SCOPE)
    try:
        await leases.register(first, user, uuid4(), uuid4())
        await leases.register(second, other, uuid4(), uuid4())
        await safety.record_stop(first, "denied")
        with pytest.raises(CommandRejected):
            async with safety.action_guard(first, other):
                pytest.fail("Wrong owner")
        with pytest.raises(CommandRejected):
            await safety.record_stop(uuid4(), "denied")
        async with safety.action_guard(second, other):
            pass
        separate = PostgresSiteSafetyStore(
            engine, SiteScope("synthetic", ("https://example.invalid",), ("example.invalid",))
        )
        async with separate.action_guard(first, user):
            pass
        with pytest.raises(SiteSafetyBlocked):
            async with safety.action_guard(first, user):
                pytest.fail("Unrelated actions must not clear a BOSS stop")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_failures_never_clear_existing_stop(database_url: str) -> None:
    engine = create_async_engine(database_url)
    session = uuid4()
    user = "safety-" + uuid4().hex
    safety = PostgresSiteSafetyStore(engine, BOSS_SCOPE)
    try:
        await PostgresLeaseStore(engine).register(session, user, uuid4(), uuid4())
        with pytest.raises(OSError):
            async with safety.action_guard(session, user):
                raise OSError("Synthetic disconnect; not safe recovery")
        await safety.record_stop(session, "abnormal")
        with pytest.raises(SiteSafetyBlocked):
            async with safety.action_guard(session, user):
                pytest.fail("Old failed/unknown action cannot resume")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_rejects_incomplete_risk_evidence(database_url: str) -> None:
    engine = create_async_engine(database_url)
    session = uuid4()
    user = "safety-" + uuid4().hex
    try:
        await PostgresLeaseStore(engine).register(session, user, uuid4(), uuid4())
        await PostgresSiteSafetyStore(engine, BOSS_SCOPE).record_stop(session, "denied")
        for column in ("reason", "session_id", "stopped_at"):
            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(f"UPDATE browser.site_safety SET {column}=NULL WHERE user_id=:user"),
                        {"user": user},
                    )
    finally:
        await engine.dispose()
