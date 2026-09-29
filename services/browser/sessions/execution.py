import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

Result = TypeVar("Result")
LifecycleStep = Callable[[], Awaitable[None]]


class ExecutorState(StrEnum):
    ACTIVE = "active"
    DRAINING = "draining"
    CLOSED = "closed"
    UNCERTAIN = "uncertain"


class ExecutorUnavailable(Exception):
    pass


class ExecutorLifecycle:
    def __init__(
        self,
        *,
        check_lease: LifecycleStep,
        mark_draining: LifecycleStep,
        disconnect: LifecycleStep,
        release: LifecycleStep,
        stop_timeout: float = 10,
    ) -> None:
        if stop_timeout <= 0:
            raise ValueError("Stop timeout must be positive")
        self._check_lease = check_lease
        self._mark_draining = mark_draining
        self._disconnect = disconnect
        self._release = release
        self._stop_timeout = stop_timeout
        self._state = ExecutorState.ACTIVE
        self._operation_lock = asyncio.Lock()

    @property
    def state(self) -> ExecutorState:
        return self._state

    async def run(self, operation: Callable[[], Awaitable[Result]]) -> Result:
        async with self._operation_lock:
            if self._state != ExecutorState.ACTIVE:
                raise ExecutorUnavailable("Executor is not accepting operations")
            completed = False
            operation_started = False
            try:
                await self._check_lease()
                if self._state != ExecutorState.ACTIVE:
                    completed = True
                    raise ExecutorUnavailable("Executor stopped while checking its lease")
                operation_started = True
                result = await operation()
                completed = True
                return result
            finally:
                if not completed and (operation_started or self._state == ExecutorState.ACTIVE):
                    self._state = ExecutorState.UNCERTAIN

    async def stop(self) -> None:
        if self._state == ExecutorState.CLOSED:
            return
        if self._state != ExecutorState.ACTIVE:
            raise ExecutorUnavailable("Executor requires reconciliation")
        self._state = ExecutorState.DRAINING
        completed = False
        try:
            async with asyncio.timeout(self._stop_timeout):
                await self._mark_draining()
                async with self._operation_lock:
                    if self._state != ExecutorState.DRAINING:
                        raise ExecutorUnavailable("In-flight operation outcome is uncertain")
                    await self._disconnect()
                    await self._release()
                    self._state = ExecutorState.CLOSED
                    completed = True
        finally:
            if not completed:
                self._state = ExecutorState.UNCERTAIN
