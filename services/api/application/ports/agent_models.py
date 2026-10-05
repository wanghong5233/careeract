from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RuntimeModel:
    id: str
    provider: str
    model: str
    label: str


class AgentModelCatalog(Protocol):
    async def list(self) -> tuple[RuntimeModel, ...]: ...

    async def require(self, model_id: str) -> RuntimeModel: ...
