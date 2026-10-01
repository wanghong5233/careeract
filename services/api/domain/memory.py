from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

MemoryKind = Literal["note", "rule"]
MemoryState = Literal["candidate", "confirmed", "retired"]
MEMORY_KINDS = frozenset({"note", "rule"})
MEMORY_STATES = frozenset({"candidate", "confirmed", "retired"})


def validate_memory_content(
    kind: MemoryKind | None,
    state: MemoryState | None,
    title: str | None,
    content: str | None,
    source: str | None = None,
) -> None:
    if kind is not None and kind not in MEMORY_KINDS:
        raise ValueError("Unknown memory kind")
    if state is not None and state not in MEMORY_STATES:
        raise ValueError("Unknown memory state")
    if title is not None and (not title.strip() or len(title) > 200):
        raise ValueError("Memory title is empty or too long")
    if content is not None and (not content.strip() or len(content) > 8000):
        raise ValueError("Memory content is empty or too long")
    if source is not None and len(source) > 200:
        raise ValueError("Memory source is too long")


@dataclass(frozen=True, slots=True)
class WorkspaceMemory:
    id: UUID
    user_id: str
    project_id: UUID | None
    kind: MemoryKind
    state: MemoryState
    title: str
    content: str
    source: str
    version: UUID
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        validate_memory_content(self.kind, self.state, self.title, self.content, self.source)


@dataclass(frozen=True, slots=True)
class MemoryPage:
    items: tuple[WorkspaceMemory, ...]
    next_cursor: str | None


class MemoryConflict(Exception):
    pass


class MemoryNotFound(Exception):
    pass


class MemoryInvalid(Exception):
    pass


class MemoryUnavailable(Exception):
    pass
