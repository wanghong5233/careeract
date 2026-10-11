from dataclasses import dataclass
from typing import Literal, Protocol

from services.api.application.ports.browser_control import BrowserControlContext


@dataclass(frozen=True, slots=True, repr=False)
class BossJobObservation:
    job_id: str
    title: str
    company: str
    location: str | None
    salary: str | None
    url: str | None


@dataclass(frozen=True, slots=True, repr=False)
class BossConversationObservation:
    conversation_id: str
    recruiter_name: str | None
    company: str | None
    job_title: str | None
    last_message: str | None
    unread: bool
    url: str | None


@dataclass(frozen=True, slots=True, repr=False)
class BossMessageObservation:
    message_id: str
    sender: Literal["recruiter", "candidate", "system", "unknown"]
    content: str
    sent_at: str | None


@dataclass(frozen=True, slots=True, repr=False)
class BossPageObservation:
    url: str
    title: str
    kind: Literal["login", "job_list", "job_detail", "conversations", "unknown"]
    state: Literal["ready", "needs_login", "risk", "unstable", "unknown"]
    jobs: tuple[BossJobObservation, ...]
    signals: tuple[str, ...]
    conversations: tuple[BossConversationObservation, ...]
    messages: tuple[BossMessageObservation, ...]


class BossPageReader(Protocol):
    async def read_boss_page(self, context: BrowserControlContext) -> BossPageObservation: ...
