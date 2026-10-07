from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from html.parser import HTMLParser
from urllib.parse import urljoin


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
class BossReadOnlyPage:
    url: str
    title: str
    kind: BossPageKind
    state: BossPageState
    jobs: tuple[BossJobSummary, ...]
    signals: tuple[str, ...]


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

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].text.append(data)


def parse_boss_page(*, html: str, url: str, title: str) -> BossReadOnlyPage:
    parser = _TreeParser()
    parser.feed(html)
    body_text = _text(parser.root)
    signals: list[str] = []

    if url == "about:blank":
        signals.append("blank_page")
        return _page(url, title, BossPageKind.UNKNOWN, BossPageState.RISK, (), signals)

    lowered_url = url.lower()
    lowered_text = body_text.lower()
    if "_security_check" in lowered_url or _contains_any(
        lowered_text, ("安全验证", "安全校验", "请完成验证", "security check")
    ):
        signals.append("security_check")
        return _page(url, title, BossPageKind.UNKNOWN, BossPageState.RISK, (), signals)

    if (
        _contains_any(lowered_url, ("/user/login", "/login"))
        or _contains_any(lowered_text, ("登录后查看", "扫码登录", "登录/注册"))
        and not _find_job_cards(parser.root)
    ):
        signals.append("login_required")
        return _page(url, title, BossPageKind.LOGIN, BossPageState.NEEDS_LOGIN, (), signals)

    if _contains_any(
        lowered_text, ("加载中，请稍候", "正在加载", "loading")
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

    signals.append("unrecognized_structure")
    return _page(url, title, BossPageKind.UNKNOWN, BossPageState.UNKNOWN, (), signals)


def _page(
    url: str,
    title: str,
    kind: BossPageKind,
    state: BossPageState,
    jobs: tuple[BossJobSummary, ...],
    signals: list[str],
) -> BossReadOnlyPage:
    return BossReadOnlyPage(url, title, kind, state, jobs, tuple(signals))


def _find_job_cards(root: _Node) -> list[_Node]:
    return [
        node
        for node in _descendants(root)
        if node.attrs.get("data-job-id")
        or "job-card" in _class_tokens(node)
        or "job-primary" in _class_tokens(node)
    ]


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
