from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

ProjectStatus = Literal["planned", "active", "paused", "completed", "archived"]
PROJECT_STATUSES = frozenset({"planned", "active", "paused", "completed", "archived"})


def validate_text(value: str, limit: int, *, required: bool = False) -> None:
    if len(value) > limit or (required and not value.strip()):
        raise ValueError("Project text is empty or exceeds its length limit")


def validate_project_content(
    title: str | None, purpose: str | None, status: ProjectStatus | None
) -> None:
    if title is not None:
        validate_text(title, 200, required=True)
    if purpose is not None:
        validate_text(purpose, 4000)
    if status is not None and status not in PROJECT_STATUSES:
        raise ValueError("Unknown project status")


@dataclass(frozen=True, slots=True)
class CareerProject:
    id: UUID
    user_id: str
    title: str
    purpose: str
    status: ProjectStatus
    version: UUID
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        validate_project_content(self.title, self.purpose, self.status)


class ProjectConflict(Exception):
    pass


class ProjectNotFound(Exception):
    pass


class ProjectInvalid(Exception):
    pass


class ProjectUnavailable(Exception):
    pass
