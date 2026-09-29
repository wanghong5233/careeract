from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


def validate_text(value: str, limit: int, *, required: bool = False) -> None:
    if len(value) > limit or (required and not value.strip()):
        raise ValueError("Profile text is empty or exceeds its length limit")


@dataclass(frozen=True, slots=True)
class ProfileEntry:
    title: str
    organization: str = ""
    period: str = ""
    details: str = ""
    evidence: str = ""

    def __post_init__(self) -> None:
        validate_text(self.title, 200, required=True)
        validate_text(self.organization, 200)
        validate_text(self.period, 100)
        validate_text(self.details, 4000)
        validate_text(self.evidence, 1000)


@dataclass(frozen=True, slots=True)
class ProfileContent:
    display_name: str = ""
    education: tuple[ProfileEntry, ...] = ()
    experience: tuple[ProfileEntry, ...] = ()
    projects: tuple[ProfileEntry, ...] = ()
    skills: str = ""
    goals: str = ""
    constraints: str = ""

    def __post_init__(self) -> None:
        validate_text(self.display_name, 100)
        for entries in (self.education, self.experience, self.projects):
            if len(entries) > 30:
                raise ValueError("At most 30 entries are allowed in each profile section")
        for value in (self.skills, self.goals, self.constraints):
            validate_text(value, 4000)


@dataclass(frozen=True, slots=True)
class CareerProfile:
    user_id: str
    content: ProfileContent
    version: UUID
    confirmed_at: datetime


class ProfileConflict(Exception):
    pass


class ProfileUnavailable(Exception):
    pass
