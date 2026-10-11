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
