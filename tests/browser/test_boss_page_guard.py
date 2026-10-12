import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.browser.sessions.authentication import BrowserCommand, CommandRejected
from services.browser.sessions.lease import LeaseConflict
from services.browser.sessions.postgres import PostgresLeaseStore
from tests.browser.test_command_authentication import command_payload
from tests.browser.test_postgres_leases import database_url as database_url

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL integration",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["drain", "revoke"])
async def test_executor_action_serializes_control_change_and_rejects_stale_writer(
    database_url: str, transition: str
) -> None:
    engine = create_async_engine(database_url)
    store = PostgresLeaseStore(engine)
    command = BrowserCommand.model_validate(
        command_payload() | {"action": "acquire", "owner_id": "synthetic-executor"}
    )
    await store.register(command.session_id, command.sub, command.task_id, command.authorization_id)
    try:
        lease = await store.execute(command)
        check = command.model_copy(update={"action": "check", "lease_id": lease.lease_id})
        for field, value in (
            ("sub", "other-user"),
            ("task_id", uuid4()),
            ("authorization_id", uuid4()),
            ("attempt_id", uuid4()),
            ("owner_id", "other-executor"),
            ("lease_id", uuid4()),
            ("action", "snapshot"),
            ("iat", 1),
        ):
            with pytest.raises((CommandRejected, LeaseConflict)):
                async with store.executor_action_guard(check.model_copy(update={field: value})):
                    pytest.fail("Invalid action must not enter browser execution")
        stop = check.model_copy(update={"action": "stop", "jti": uuid4()})
        async with store.executor_action_guard(check):
            changing = asyncio.create_task(
                store.execute(stop) if transition == "drain" else store.revoke(command.session_id)
            )
            await asyncio.sleep(0.1)
            assert not changing.done()
        await changing
        with pytest.raises((CommandRejected, LeaseConflict)):
            async with store.executor_action_guard(check):
                pytest.fail("Stopped writer must not admit another action")
        await store.confirm_stopped(command.session_id, lease.lease_id)
        if transition == "drain":
            replacement = command.model_copy(update={"attempt_id": uuid4(), "jti": uuid4()})
            next_lease = await store.execute(replacement)
            with pytest.raises(LeaseConflict):
                async with store.executor_action_guard(check):
                    pytest.fail("Old generation must not admit actions")
            await store.execute(
                replacement.model_copy(
                    update={"action": "stop", "lease_id": next_lease.lease_id, "jti": uuid4()}
                )
            )
            await store.confirm_stopped(command.session_id, next_lease.lease_id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_snapshot_excludes_writer_and_revocation_waits_for_capture(database_url: str) -> None:
    engine = create_async_engine(database_url)
    store = PostgresLeaseStore(engine)
    command = BrowserCommand.model_validate(
        command_payload()
        | {
            "action": "snapshot",
            "owner_id": "synthetic-page-reader",
        }
    )
    await store.register(command.session_id, command.sub, command.task_id, command.authorization_id)
    try:
        for field in ("sub", "task_id", "authorization_id"):
            with pytest.raises(CommandRejected):
                async with store.snapshot_guard(command.model_copy(update={field: str(uuid4())})):
                    pytest.fail("Wrong ownership must not enter capture")
        async with store.snapshot_guard(command):
            revoking = asyncio.create_task(store.revoke(command.session_id))
            await asyncio.sleep(0.1)
            assert not revoking.done()
        await revoking
        with pytest.raises(CommandRejected):
            async with store.snapshot_guard(command):
                pytest.fail("Revoked session must not enter capture")
        second = command.model_copy(update={"session_id": uuid4(), "jti": uuid4()})
        await store.register(second.session_id, second.sub, second.task_id, second.authorization_id)
        lease = await store.execute(second.model_copy(update={"action": "acquire"}))
        with pytest.raises(LeaseConflict):
            async with store.snapshot_guard(second):
                pytest.fail("Active writer must exclude capture")
        await store.execute(
            second.model_copy(
                update={
                    "action": "stop",
                    "lease_id": lease.lease_id,
                    "jti": uuid4(),
                }
            )
        )
        with pytest.raises(LeaseConflict):
            async with store.snapshot_guard(second):
                pytest.fail("Draining writer must exclude capture")
        await store.confirm_stopped(second.session_id, lease.lease_id)
        async with store.snapshot_guard(second):
            pass
        third = command.model_copy(update={"session_id": uuid4(), "jti": uuid4()})
        await store.register(third.session_id, third.sub, third.task_id, third.authorization_id)
        async with store.snapshot_guard(third):
            acquiring = asyncio.create_task(
                store.execute(third.model_copy(update={"action": "acquire"}))
            )
            await asyncio.sleep(0.1)
            assert not acquiring.done()
        acquired = await acquiring
        assert acquired.session_id == third.session_id
        async with engine.connect() as database:
            database_time = int(
                await database.scalar(text("SELECT EXTRACT(EPOCH FROM clock_timestamp())"))
            )
        expiring = command.model_copy(
            update={
                "session_id": uuid4(),
                "jti": uuid4(),
                "iat": database_time,
                "exp": database_time + 2,
            }
        )
        await store.register(
            expiring.session_id, expiring.sub, expiring.task_id, expiring.authorization_id
        )
        with pytest.raises(CommandRejected, match="expired"):
            async with store.snapshot_guard(expiring):
                await asyncio.sleep(2.1)
    finally:
        await engine.dispose()
