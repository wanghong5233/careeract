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
    last_message_id: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class BossResumeAttachmentObservation:
    # A rendered message reference, not a delivery receipt or current material identity.
    filename: str
    sent_by_candidate: bool
    request_message_id: str | None


@dataclass(frozen=True, slots=True, repr=False)
class BossMessageObservation:
    message_id: str
    sender: Literal["recruiter", "candidate", "system", "unknown"]
    content: str
    sent_at: str | None
    conversation_id: str | None = None
    resume_attachment: BossResumeAttachmentObservation | None = None


@dataclass(frozen=True, slots=True, repr=False)
class BossResumeControlObservation:
    conversation_id: str
    state: Literal["available", "unavailable", "unknown"]
    attachment_reported: bool | None
    material_state: Literal["present_unidentified", "absent", "unknown"] = "unknown"


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
    resume_control: BossResumeControlObservation | None = None


class BossPageReader(Protocol):
    async def read_boss_page(self, context: BrowserControlContext) -> BossPageObservation: ...


def has_bound_conversation_messages(page: BossPageObservation) -> bool:
    conversation_ids = [item.conversation_id for item in page.conversations]
    message_keys = [(item.conversation_id, item.message_id) for item in page.messages]
    return (
        bool(conversation_ids)
        and bool(message_keys)
        and all(conversation_ids)
        and len(set(conversation_ids)) == len(conversation_ids)
        and len(set(message_keys)) == len(message_keys)
        and all(
            message.conversation_id in conversation_ids
            and bool(message.message_id)
            and bool(message.content.strip())
            and message.sender != "unknown"
            and (
                message.resume_attachment is None
                or message.resume_attachment.filename in message.content
                and bool(message.resume_attachment.filename.strip())
                and len(message.resume_attachment.filename) <= 300
                and not any(
                    ord(character) < 32 or ord(character) == 127 or character in "/\\"
                    for character in message.resume_attachment.filename
                )
                and (
                    message.sender == "system"
                    or message.resume_attachment.sent_by_candidate
                    == (message.sender == "candidate")
                )
                and (
                    message.resume_attachment.request_message_id is None
                    or message.resume_attachment.request_message_id.isascii()
                    and message.resume_attachment.request_message_id.isdecimal()
                    and not message.resume_attachment.request_message_id.startswith("0")
                    and len(message.resume_attachment.request_message_id) <= 20
                )
            )
            for message in page.messages
        )
    )
