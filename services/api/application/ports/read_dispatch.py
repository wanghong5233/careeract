from typing import Protocol
from uuid import UUID


class ReadDispatcher(Protocol):
    async def dispatch(self, task_id: UUID) -> None: ...
