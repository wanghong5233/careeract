from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class BossPageKind(StrEnum):
    LOGIN = "login"
    JOB_LIST = "job_list"
    JOB_DETAIL = "job_detail"
    CONVERSATIONS = "conversations"
    UNKNOWN = "unknown"


class BossPageState(StrEnum):
    READY = "ready"
    NEEDS_LOGIN = "needs_login"
    RISK = "risk"
    UNSTABLE = "unstable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BossJobSummary:
    job_id: str
    title: str
    company: str
    location: str | None
    salary: str | None
    url: str | None


@dataclass(frozen=True, slots=True)
class BossConversationSummary:
    conversation_id: str
    recruiter_name: str | None
    company: str | None
    job_title: str | None
    last_message: str | None
    unread: bool
    url: str | None
    last_message_id: str | None = None


@dataclass(frozen=True, slots=True)
class BossResumeAttachment:
    # isSelf binds the card's message side; it does not establish successful delivery.
    filename: str
    sent_by_candidate: bool
    request_message_id: str | None


@dataclass(frozen=True, slots=True)
class BossMessageSummary:
    message_id: str
    sender: Literal["recruiter", "candidate", "system", "unknown"]
    content: str
    sent_at: str | None
    conversation_id: str | None = None
    resume_attachment: BossResumeAttachment | None = None


@dataclass(frozen=True, slots=True)
class BossResumeControl:
    conversation_id: str
    state: Literal["available", "unavailable", "unknown"]
    attachment_reported: bool | None


@dataclass(frozen=True, slots=True)
class BossReadOnlyPage:
    url: str
    title: str
    kind: BossPageKind
    state: BossPageState
    jobs: tuple[BossJobSummary, ...]
    signals: tuple[str, ...]
    conversations: tuple[BossConversationSummary, ...] = ()
    messages: tuple[BossMessageSummary, ...] = ()
    resume_control: BossResumeControl | None = None


class _RenderedConversation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    conversation_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    recruiter_name: str = Field(min_length=1, max_length=200)
    last_message: str = Field(max_length=10000)
    last_message_id: str = Field(min_length=1, max_length=20, pattern=r"^[1-9][0-9]*$")
    unread: bool


class _RenderedResumeAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    filename: str = Field(min_length=1, max_length=300, pattern=r"^[^\x00-\x1f\x7f/\\]+$")
    sent_by_candidate: bool
    request_message_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,19}$")


class _RenderedMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    conversation_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    message_id: str = Field(min_length=1, max_length=20, pattern=r"^[1-9][0-9]*$")
    sender: Literal["recruiter", "candidate", "system"]
    content: str = Field(min_length=1, max_length=10000)
    sent_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
    resume_attachment: _RenderedResumeAttachment | None = None


class _RenderedResumeControl(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    conversation_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    last_message_id: str = Field(min_length=1, max_length=20, pattern=r"^[1-9][0-9]*$")
    state: Literal["available", "unavailable", "unknown"]
    attachment_reported: bool | None


def parse_boss_resume_control(
    value: str, messages: tuple[BossMessageSummary, ...], conversation_id: str
) -> BossResumeControl:
    if len(value.encode("utf-8")) > 2048:
        raise ValueError("BOSS resume control exceeds capture limit")
    control = _RenderedResumeControl.model_validate_json(value)
    if (
        not messages
        or control.conversation_id != conversation_id
        or messages[-1].conversation_id != conversation_id
        or control.last_message_id != messages[-1].message_id
    ):
        raise ValueError("BOSS resume control binding is incomplete")
    return BossResumeControl(control.conversation_id, control.state, control.attachment_reported)


def parse_boss_rendered_messages(
    value: str, conversations: tuple[BossConversationSummary, ...], conversation_id: str
) -> tuple[BossMessageSummary, ...]:
    if len(value.encode("utf-8")) > 512 * 1024:
        raise ValueError("BOSS rendered messages exceed capture limit")
    rows = TypeAdapter(list[_RenderedMessage]).validate_json(value)
    target = [item for item in conversations if item.conversation_id == conversation_id]
    if not rows:
        return ()
    if (
        len(target) != 1
        or len(rows) > 200
        or len({item.message_id for item in rows}) != len(rows)
        or any(item.conversation_id != conversation_id or not item.content.strip() for item in rows)
        or rows[-1].message_id != target[0].last_message_id
    ):
        raise ValueError("BOSS rendered message binding is incomplete")
    if any(
        row.resume_attachment is not None
        and (
            row.resume_attachment.filename not in row.content
            or row.sender == "candidate"
            and not row.resume_attachment.sent_by_candidate
            or row.sender == "recruiter"
            and row.resume_attachment.sent_by_candidate
        )
        for row in rows
    ):
        raise ValueError("BOSS resume attachment binding is incomplete")
    return tuple(
        BossMessageSummary(
            row.message_id,
            row.sender,
            row.content,
            row.sent_at,
            row.conversation_id,
            BossResumeAttachment(**row.resume_attachment.model_dump())
            if row.resume_attachment is not None
            else None,
        )
        for row in rows
    )


def parse_boss_rendered_conversations(value: str) -> tuple[BossConversationSummary, ...]:
    if len(value.encode("utf-8")) > 512 * 1024:
        raise ValueError("BOSS rendered conversation capture is too large")
    rows = TypeAdapter(list[_RenderedConversation]).validate_json(value)
    if len(rows) > 200 or len({row.conversation_id for row in rows}) != len(rows):
        raise ValueError("BOSS rendered conversation identities are ambiguous")
    return tuple(
        BossConversationSummary(
            conversation_id=row.conversation_id,
            recruiter_name=row.recruiter_name,
            company=None,
            job_title=None,
            last_message=row.last_message or None,
            unread=row.unread,
            url="https://www.zhipin.com/web/geek/chat",
            last_message_id=row.last_message_id,
        )
        for row in rows
    )


@dataclass(slots=True)
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list[_Node]
    text: list[str]


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", {}, [], [])
        self._stack = [self.root]
        self._ignored_tag: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._ignored_tag is not None:
            return
        if tag in {"script", "style"}:
            self._ignored_tag = tag
            return
        node = _Node(tag, {key: value or "" for key, value in attrs}, [], [])
        self._stack[-1].children.append(node)
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._stack[-1].tag == tag:
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if self._ignored_tag is not None:
            if tag == self._ignored_tag:
                self._ignored_tag = None
            return
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self._ignored_tag is not None:
            return
        self._stack[-1].text.append(data)


def boss_auth_page_state(url: str) -> BossPageState | None:
    path = urlsplit(url).path.lower()
    if any(marker in path for marker in ("_security_check", "/verify", "/security")):
        return BossPageState.RISK
    if any(marker in path for marker in ("/web/user/", "/user/login", "/login", "/passport/")):
        return BossPageState.NEEDS_LOGIN
    return None


def parse_boss_page(
    *,
    html: str,
    url: str,
    title: str,
    rendered_conversations: tuple[BossConversationSummary, ...] = (),
    rendered_messages: tuple[BossMessageSummary, ...] = (),
) -> BossReadOnlyPage:
    parser = _TreeParser()
    parser.feed(html)
    body_text = _text(parser.root)
    signals: list[str] = []

    if url == "about:blank":
        signals.append("blank_page")
        return _page(url, title, BossPageKind.UNKNOWN, BossPageState.RISK, (), signals)

    auth_state = boss_auth_page_state(url)
    lowered_text = body_text.lower()
    nodes = _descendants(parser.root)
    authenticated_navigation = any(
        _class_tokens(node) & {"nav-figure", "user-nav"} for node in nodes
    ) and any(node.tag == "a" and "/web/geek/chat" in node.attrs.get("href", "") for node in nodes)
    if auth_state == BossPageState.RISK or _contains_any(
        lowered_text, ("安全验证", "安全校验", "请完成验证", "security check")
    ):
        signals.append("security_check")
        return _page(url, title, BossPageKind.UNKNOWN, BossPageState.RISK, (), signals)

    if (
        auth_state == BossPageState.NEEDS_LOGIN
        or _contains_any(lowered_text, ("登录后查看", "扫码登录", "登录/注册"))
        and not _find_job_cards(parser.root)
        and not authenticated_navigation
    ):
        signals.append("login_required")
        return _page(url, title, BossPageKind.LOGIN, BossPageState.NEEDS_LOGIN, (), signals)

    if (
        _contains_any(lowered_text, ("加载中，请稍候", "正在加载")) or lowered_text == "loading"
    ) and not _find_job_cards(parser.root):
        signals.append("page_loading")
        return _page(url, title, BossPageKind.UNKNOWN, BossPageState.UNSTABLE, (), signals)

    cards = _find_job_cards(parser.root)
    jobs_list: list[BossJobSummary] = []
    for card in cards:
        job = _job_summary(card, url)
        if job is not None:
            jobs_list.append(job)
    jobs = tuple(jobs_list)
    if jobs:
        signals.append("job_cards")
        return _page(url, title, BossPageKind.JOB_LIST, BossPageState.READY, jobs, signals)

    conversations = tuple(
        conversation
        for card in _find_conversation_cards(parser.root)
        if (conversation := _conversation_summary(card, url)) is not None
    )
    messages = tuple(
        message for node in _find_message_nodes(parser.root) if (message := _message_summary(node))
    )
    if conversations or messages:
        signals.append("conversation_data")
        return _page(
            url,
            title,
            BossPageKind.CONVERSATIONS,
            BossPageState.READY,
            (),
            signals,
            conversations,
            messages,
        )

    if _has_conversation_structure(nodes) and rendered_conversations:
        signals.append(
            "rendered_conversation_messages"
            if rendered_messages
            else "rendered_conversation_previews"
        )
        return _page(
            url,
            title,
            BossPageKind.CONVERSATIONS,
            BossPageState.READY if rendered_messages else BossPageState.UNKNOWN,
            (),
            signals,
            rendered_conversations,
            rendered_messages,
        )

    if _has_conversation_structure(nodes):
        signals.append("conversation_structure")
        _log_conversation_structure(nodes)
        return _page(url, title, BossPageKind.CONVERSATIONS, BossPageState.UNKNOWN, (), signals)

    signals.append("unrecognized_structure")
    structural_classes = sorted(
        {
            token
            for node in nodes
            for token in _class_tokens(node)
            if token.startswith(("chat-", "message-", "conversation-", "friend-", "session-"))
            and re.fullmatch(r"[a-z][a-z0-9-]{0,50}", token)
        }
    )[:40]
    logging.getLogger(__name__).warning(
        "BOSS page structure unrecognized classes=%s", ",".join(structural_classes)
    )
    return _page(url, title, BossPageKind.UNKNOWN, BossPageState.UNKNOWN, (), signals)


def _page(
    url: str,
    title: str,
    kind: BossPageKind,
    state: BossPageState,
    jobs: tuple[BossJobSummary, ...],
    signals: list[str],
    conversations: tuple[BossConversationSummary, ...] = (),
    messages: tuple[BossMessageSummary, ...] = (),
) -> BossReadOnlyPage:
    return BossReadOnlyPage(url, title, kind, state, jobs, tuple(signals), conversations, messages)


def _find_job_cards(root: _Node) -> list[_Node]:
    return [
        node
        for node in _descendants(root)
        if node.attrs.get("data-job-id")
        or "job-card" in _class_tokens(node)
        or "job-primary" in _class_tokens(node)
    ]


def _find_conversation_cards(root: _Node) -> list[_Node]:
    return [
        node
        for node in _descendants(root)
        if node.attrs.get("data-conversation-id")
        and not node.attrs.get("data-message-id")
        or "conversation-item" in _class_tokens(node)
        or "chat-item" in _class_tokens(node)
    ]


def _find_message_nodes(root: _Node) -> list[_Node]:
    return [
        node
        for node in _descendants(root)
        if node.attrs.get("data-message-id")
        or "message-item" in _class_tokens(node)
        or "message-content" in _class_tokens(node)
    ]


def _has_conversation_structure(nodes: list[_Node]) -> bool:
    classes = {token for node in nodes for token in _class_tokens(node)}
    return {
        "chat-container",
        "chat-content",
        "chat-conversation",
    }.issubset(classes) and bool({"friend-content", "friend-content-warp", "chat-user"} & classes)


def _log_conversation_structure(nodes: list[_Node]) -> None:
    containers = [
        node
        for node in nodes
        if "friend-content-warp" in _class_tokens(node)
        or any("friend-content" in _class_tokens(child) for child in node.children)
    ]
    structure: list[str] = []
    for container in containers[:1]:
        for node in [container, *_descendants(container)][:80]:
            classes = sorted(
                token
                for token in _class_tokens(node)
                if re.fullmatch(r"[a-z][a-z0-9-]{0,50}", token)
            )[:6]
            attributes = sorted(node.attrs)[:12]
            structure.append(f"{node.tag}[{','.join(classes)}]({','.join(attributes)})")
    for node in nodes:
        if "friend-content" in _class_tokens(node):
            parent = next(
                (candidate for candidate in nodes if node in candidate.children),
                None,
            )
            if parent is not None:
                parent_classes = ",".join(sorted(_class_tokens(parent))[:8])
                parent_attrs = ",".join(sorted(parent.attrs)[:12])
                structure.append("parent:" + f"{parent.tag}[{parent_classes}]({parent_attrs})")
            break
    logging.getLogger(__name__).warning(
        "BOSS conversation structure without bound rows nodes=%s", ";".join(structure)
    )


def _job_summary(card: _Node, base_url: str) -> BossJobSummary | None:
    job_id = card.attrs.get("data-job-id", "").strip()
    title = _field_text(card, "title", ("job-name", "job-title"))
    company = _field_text(card, "company", ("company-name",))
    if not job_id or not title or not company:
        return None
    location = _field_text(card, "location", ("job-area", "location"))
    salary = _field_text(card, "salary", ("salary",))
    link = next(
        (
            node.attrs.get("href")
            for node in _descendants(card)
            if node.tag == "a" and node.attrs.get("href")
        ),
        None,
    )
    return BossJobSummary(
        job_id, title, company, location, salary, urljoin(base_url, link) if link else None
    )


def _conversation_summary(card: _Node, base_url: str) -> BossConversationSummary | None:
    conversation_id = card.attrs.get("data-conversation-id", "").strip()
    if not conversation_id:
        return None
    link = next(
        (
            node.attrs.get("href")
            for node in _descendants(card)
            if node.tag == "a" and node.attrs.get("href")
        ),
        None,
    )
    unread_value = card.attrs.get("data-unread", "").strip().lower()
    unread = unread_value in {"1", "true", "yes"} or "unread" in _class_tokens(card)
    return BossConversationSummary(
        conversation_id=conversation_id,
        recruiter_name=_field_text(card, "recruiter", ("recruiter-name", "user-name")),
        company=_field_text(card, "company", ("company-name",)),
        job_title=_field_text(card, "job", ("job-name", "job-title")),
        last_message=_field_text(card, "last-message", ("last-message", "message-preview")),
        unread=unread,
        url=urljoin(base_url, link) if link else None,
    )


def _message_summary(node: _Node) -> BossMessageSummary | None:
    message_id = node.attrs.get("data-message-id", "").strip()
    content = _text(node)
    if not message_id or not content:
        return None
    sender_value = node.attrs.get("data-sender", "").strip().lower()
    sender: Literal["recruiter", "candidate", "system", "unknown"]
    if sender_value in {"recruiter", "hr", "boss"}:
        sender = "recruiter"
    elif sender_value in {"candidate", "me", "self", "user"}:
        sender = "candidate"
    elif sender_value == "system":
        sender = "system"
    else:
        sender = "unknown"
    return BossMessageSummary(
        message_id=message_id,
        sender=sender,
        content=content,
        sent_at=node.attrs.get("data-sent-at") or _field_text(node, "sent-at", ("message-time",)),
        conversation_id=node.attrs.get("data-conversation-id") or None,
    )


def _field_text(node: _Node, field: str, classes: tuple[str, ...]) -> str | None:
    for candidate in _descendants(node):
        if candidate.attrs.get("data-field") == field or any(
            token in _class_tokens(candidate) for token in classes
        ):
            value = _text(candidate)
            if value:
                return value
    return None


def _class_tokens(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _descendants(node: _Node) -> list[_Node]:
    result: list[_Node] = []
    for child in node.children:
        result.append(child)
        result.extend(_descendants(child))
    return result


def _text(node: _Node) -> str:
    parts = list(node.text)
    for child in node.children:
        parts.append(_text(child))
    return " ".join(" ".join(parts).split())


def _contains_any(value: str, candidates: tuple[str, ...]) -> bool:
    return any(candidate in value for candidate in candidates)
