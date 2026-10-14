from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

ReplyState = Literal[
    "accepted", "running", "waiting", "completed", "failed", "timed_out", "cancelled"
]
ReplyCategory = Literal[
    "routine",
    "acknowledgement",
    "resume_request",
    "commitment",
    "technical",
    "unknown",
    "no_action",
]


@dataclass(frozen=True, slots=True, repr=False)
class ReplyFact:
    field: str
    quote: str


@dataclass(frozen=True, slots=True, repr=False)
class ReplyDecision:
    category: ReplyCategory
    text: str
    reason: str
    facts: tuple[ReplyFact, ...]


@dataclass(frozen=True, slots=True, repr=False)
class CommunicationReply:
    id: UUID
    user_id: str
    connection_id: UUID
    read_task_id: UUID
    conversation_id: str
    message_id: str
    request_key: UUID
    version: UUID
    status: ReplyState
    outcome: str | None
    decision: ReplyDecision | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ReplyPage:
    items: tuple[CommunicationReply, ...]
    next_cursor: UUID | None


class CommunicationInvalid(Exception):
    pass


class CommunicationConflict(Exception):
    pass


class CommunicationNotFound(Exception):
    pass


class CommunicationUnavailable(Exception):
    pass


def validate_reply_decision(
    decision: ReplyDecision, profile_facts: dict[str, str]
) -> ReplyDecision:
    """Model citations are checked against the captured confirmed profile, never history."""
    if (
        decision.category
        not in {
            "routine",
            "acknowledgement",
            "resume_request",
            "commitment",
            "technical",
            "unknown",
            "no_action",
        }
        or not decision.reason.strip()
        or len(decision.reason) > 1000
        or len(decision.text) > 1000
        or len(decision.facts) > 20
    ):
        raise CommunicationInvalid("Reply decision exceeds its contract")
    for fact in decision.facts:
        if (
            not fact.quote.strip()
            or fact.field in {"goals", "constraints"}
            or fact.field not in profile_facts
            or fact.quote not in profile_facts[fact.field]
        ):
            raise CommunicationInvalid("Reply fact has no confirmed source")
    if decision.category == "routine":
        if not decision.text.strip() or not decision.facts:
            raise CommunicationInvalid("A factual reply requires confirmed references")
    elif decision.category == "acknowledgement":
        raise CommunicationInvalid("Neutral acknowledgements are no longer permitted")
    elif decision.text or decision.facts:
        raise CommunicationInvalid("An unresolved decision cannot contain a sendable reply")
    return decision


def is_factual_reply(decision: ReplyDecision | None, profile_facts: dict[str, str]) -> bool:
    if decision is None or decision.category != "routine":
        return False
    try:
        validate_reply_decision(decision, profile_facts)
    except CommunicationInvalid:
        return False
    return True
