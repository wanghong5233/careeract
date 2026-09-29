import asyncio
from collections.abc import Awaitable, Callable

import pytest

from services.browser.sessions.execution import (
    ExecutorLifecycle,
    ExecutorState,
    ExecutorUnavailable,
)


def lifecycle(
    events: list[str],
    *,
    timeout: float = 1,
    disconnect: Callable[[], Awaitable[None]] | None = None,
) -> ExecutorLifecycle:
    async def check() -> None:
        events.append("check")

    async def drain() -> None:
        events.append("drain")

    async def close() -> None:
        events.append("disconnect")

    async def release() -> None:
        events.append("release")

    return ExecutorLifecycle(
        check_lease=check,
        mark_draining=drain,
        disconnect=disconnect or close,
        release=release,
        stop_timeout=timeout,
    )


@pytest.mark.asyncio
async def test_stop_waits_for_current_operation_and_blocks_queued_work() -> None:
    events: list[str] = []
    executor = lifecycle(events)
    started = asyncio.Event()
    finish = asyncio.Event()

    async def operation() -> None:
        started.set()
        await finish.wait()
        events.append("finished")

    running = asyncio.create_task(executor.run(operation))
    await started.wait()
    queued = asyncio.create_task(executor.run(operation))
    stopping = asyncio.create_task(executor.stop())
    await asyncio.sleep(0)
    assert executor.state == ExecutorState.DRAINING
    assert "release" not in events
    finish.set()
    await running
    with pytest.raises(ExecutorUnavailable):
        await queued
    await stopping
    assert events == ["check", "drain", "finished", "disconnect", "release"]
    await executor.stop()
    assert events.count("release") == 1
    with pytest.raises(ExecutorUnavailable):
        await executor.run(operation)


@pytest.mark.asyncio
async def test_stop_timeout_does_not_cancel_operation_or_release_owner() -> None:
    events: list[str] = []
    executor = lifecycle(events, timeout=0.02)
    started = asyncio.Event()
    finish = asyncio.Event()

    async def operation() -> None:
        started.set()
        await finish.wait()

    running = asyncio.create_task(executor.run(operation))
    await started.wait()
    with pytest.raises(TimeoutError):
        await executor.stop()
    assert not running.done()
    finish.set()
    await running
    assert executor.state == ExecutorState.UNCERTAIN
    assert events == ["check", "drain"]
    with pytest.raises(ExecutorUnavailable):
        await executor.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_failure_or_cancellation_during_disconnect_never_releases(cancel: bool) -> None:
    events: list[str] = []
    started = asyncio.Event()

    async def disconnect() -> None:
        started.set()
        if cancel:
            await asyncio.Event().wait()
        raise OSError("Synthetic disconnect failure")

    executor = lifecycle(events, disconnect=disconnect)
    stopping = asyncio.create_task(executor.stop())
    await started.wait()
    if cancel:
        stopping.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stopping
    else:
        with pytest.raises(OSError):
            await stopping
    assert executor.state == ExecutorState.UNCERTAIN
    assert "release" not in events


@pytest.mark.asyncio
async def test_failed_in_flight_operation_prevents_handoff() -> None:
    events: list[str] = []
    executor = lifecycle(events)
    started = asyncio.Event()
    finish = asyncio.Event()

    async def operation() -> None:
        started.set()
        await finish.wait()
        raise OSError("Outcome unknown")

    running = asyncio.create_task(executor.run(operation))
    await started.wait()
    stopping = asyncio.create_task(executor.stop())
    await asyncio.sleep(0)
    finish.set()
    with pytest.raises(OSError):
        await running
    with pytest.raises(ExecutorUnavailable):
        await stopping
    assert executor.state == ExecutorState.UNCERTAIN
    assert "release" not in events


@pytest.mark.asyncio
async def test_stop_during_lease_check_prevents_action_but_can_finish_cleanup() -> None:
    checking = asyncio.Event()
    checked = asyncio.Event()
    events: list[str] = []

    async def check() -> None:
        checking.set()
        await checked.wait()

    async def drain() -> None:
        events.append("drain")

    async def disconnect() -> None:
        events.append("disconnect")

    async def release() -> None:
        events.append("release")

    async def operation() -> None:
        events.append("operation")

    executor = ExecutorLifecycle(
        check_lease=check, mark_draining=drain, disconnect=disconnect, release=release
    )
    running = asyncio.create_task(executor.run(operation))
    await checking.wait()
    stopping = asyncio.create_task(executor.stop())
    await asyncio.sleep(0)
    checked.set()
    with pytest.raises(ExecutorUnavailable):
        await running
    await stopping
    assert events == ["drain", "disconnect", "release"]
    assert executor.state == ExecutorState.CLOSED
