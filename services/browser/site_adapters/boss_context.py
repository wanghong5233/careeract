import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import cast
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
from cdp_use import CDPClient
from pydantic import AnyHttpUrl
from websockets.exceptions import WebSocketException

from services.browser.sessions.context import SiteScope
from services.browser.sessions.steel import SessionsResponse
from services.browser.site_adapters.boss import (
    BossConversationSummary,
    BossMessageSummary,
    BossPageState,
    BossReadOnlyPage,
    BossResumeControl,
    boss_auth_page_state,
    parse_boss_page,
    parse_boss_rendered_conversations,
    parse_boss_rendered_messages,
    parse_boss_resume_control,
)

BOSS_SCOPE = SiteScope("boss", ("https://www.zhipin.com",), ("zhipin.com", "www.zhipin.com"))
MAX_PAGE_SNAPSHOT_BYTES = 4 * 1024 * 1024
logger = logging.getLogger(__name__)


class BossContextUnavailable(Exception):
    pass


class BossDisconnectUnconfirmed(BossContextUnavailable):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class BossPageSnapshot:
    url: str
    title: str
    html: str
    conversations: tuple[BossConversationSummary, ...] = ()
    messages: tuple[BossMessageSummary, ...] = ()
    resume_control: BossResumeControl | None = None


class BossContextReader:
    def __init__(
        self,
        client: httpx.AsyncClient,
        cdp_origin: AnyHttpUrl,
        session_id: UUID,
        *,
        include_local_storage: bool = True,
    ) -> None:
        self.client = client
        self.cdp_origin = str(cdp_origin).rstrip("/")
        self.session_id = session_id
        self.include_local_storage = include_local_storage

    async def storage_state(self) -> object:
        try:
            return await self._storage_state()
        except (
            httpx.HTTPError,
            WebSocketException,
            OSError,
            TimeoutError,
            RuntimeError,
            ValueError,
        ) as failure:
            logger.warning(
                "BOSS context capture failed session=%s boundary=%s",
                self.session_id,
                type(failure).__name__,
            )
            raise BossContextUnavailable("BOSS context capture unavailable") from None

    async def page_snapshot(self) -> BossPageSnapshot:
        try:
            return await self._page_snapshot()
        except (
            httpx.HTTPError,
            WebSocketException,
            OSError,
            TimeoutError,
            RuntimeError,
            ValueError,
        ) as failure:
            reasons = {
                "Browser context requires its owned session",
                "Browser discovery rejected",
                "Browser context requires its owned page",
                "Browser context is outside its site",
                "BOSS page changed during capture",
                "BOSS page snapshot is incomplete",
                "BOSS page snapshot is outside its site",
                "BOSS page snapshot is too large",
            }
            reason = (
                str(failure)
                if isinstance(failure, ValueError) and str(failure) in reasons
                else type(failure).__name__
            )
            logger.warning("BOSS page capture failed session=%s reason=%s", self.session_id, reason)
            raise BossContextUnavailable("BOSS page capture unavailable") from None

    async def read_page(self) -> BossReadOnlyPage:
        try:
            async with asyncio.timeout(15):
                for capture_index in range(3):
                    snapshot = await self.page_snapshot()
                    page = parse_boss_page(
                        url=snapshot.url,
                        title=snapshot.title,
                        html=snapshot.html,
                        rendered_conversations=snapshot.conversations,
                        rendered_messages=snapshot.messages,
                    )
                    if (
                        page.state not in {BossPageState.UNSTABLE, BossPageState.UNKNOWN}
                        or page.conversations
                        or capture_index == 2
                    ):
                        return page
                    await asyncio.sleep(1)
        except TimeoutError:
            logger.warning("BOSS page observation timed out session=%s", self.session_id)
            raise BossContextUnavailable("BOSS page observation unavailable") from None
        raise BossContextUnavailable("BOSS page observation unavailable")

    async def read_conversation(self, conversation_id: str) -> BossReadOnlyPage:
        try:
            snapshot = await self._page_snapshot(conversation_id=conversation_id)
            page = parse_boss_page(
                url=snapshot.url,
                title=snapshot.title,
                html=snapshot.html,
                rendered_conversations=snapshot.conversations,
                rendered_messages=snapshot.messages,
            )
            return replace(page, resume_control=snapshot.resume_control)
        except BossDisconnectUnconfirmed:
            raise
        except (
            httpx.HTTPError,
            WebSocketException,
            OSError,
            TimeoutError,
            RuntimeError,
            ValueError,
        ):
            raise BossContextUnavailable("BOSS conversation observation unavailable") from None

    async def _storage_state(self) -> object:
        inventory = await self.client.get("/v1/sessions", follow_redirects=False, timeout=5)
        inventory.raise_for_status()
        active = [
            session
            for session in SessionsResponse.model_validate_json(inventory.content).sessions
            if session.status in {"live", "idle"}
        ]
        if len(active) != 1 or active[0].id != self.session_id or active[0].status != "live":
            raise ValueError("Browser context requires its owned session")
        async with httpx.AsyncClient(base_url=self.cdp_origin, timeout=5) as discovery:
            response = await discovery.get(
                "/json/version", headers={"Host": "localhost"}, follow_redirects=False
            )
            response.raise_for_status()
            discovered = urlsplit(response.json()["webSocketDebuggerUrl"])
        if discovered.scheme not in {"ws", "wss"} or not discovered.path.startswith(
            "/devtools/browser/"
        ):
            raise ValueError("Browser discovery rejected")
        configured = urlsplit(self.cdp_origin)
        endpoint = urlunsplit(
            (
                "wss" if configured.scheme == "https" else "ws",
                configured.netloc,
                discovered.path,
                "",
                "",
            )
        )
        cdp = CDPClient(endpoint)
        stage = "connect"
        try:
            async with asyncio.timeout(8):
                await cast(Callable[[], Awaitable[None]], cdp.start)()
                stage = "page_ownership"
                targets = await cdp.send.Target.getTargets()
                pages = [target for target in targets["targetInfos"] if target["type"] == "page"]
                if len(pages) != 1:
                    raise ValueError("Browser context requires its owned page")
                page_id = pages[0]["targetId"]
                page_url = urlsplit(pages[0]["url"])
                if "https://" + str(page_url.hostname) not in BOSS_SCOPE.origins or (
                    page_url.scheme != "https"
                ):
                    raise ValueError("Browser context is outside its site")
                attached = await cdp.send.Target.attachToTarget(
                    params={"targetId": page_id, "flatten": True}
                )
                stage = "cookies"
                cookies = await cdp.send.Network.getAllCookies(session_id=attached["sessionId"])
                if not self.include_local_storage:
                    return {"cookies": cookies["cookies"], "origins": []}
                stage = "local_storage"
                try:
                    async with asyncio.timeout(2):
                        storage = await cdp.send.DOMStorage.getDOMStorageItems(
                            params={
                                "storageId": {
                                    "securityOrigin": BOSS_SCOPE.origins[0],
                                    "isLocalStorage": True,
                                }
                            },
                            session_id=attached["sessionId"],
                        )
                except TimeoutError:
                    logger.warning(
                        "BOSS local storage unavailable session=%s boundary=TimeoutError",
                        self.session_id,
                    )
                    storage = {"entries": []}
                stage = "login_verification"
                document = await cdp.send.DOM.getDocument(session_id=attached["sessionId"])
                account = await cdp.send.DOM.querySelector(
                    params={
                        "nodeId": document["root"]["nodeId"],
                        "selector": ".nav-figure, .user-nav",
                    },
                    session_id=attached["sessionId"],
                )
                messages = await cdp.send.DOM.querySelector(
                    params={
                        "nodeId": document["root"]["nodeId"],
                        "selector": 'a[href*="/web/geek/chat"]',
                    },
                    session_id=attached["sessionId"],
                )
                return {
                    "authenticated": account["nodeId"] > 0
                    and messages["nodeId"] > 0
                    and not any(
                        marker in page_url.path
                        for marker in ("/passport/", "/login", "/verify", "/security")
                    ),
                    "cookies": cookies["cookies"],
                    "origins": [
                        {
                            "origin": BOSS_SCOPE.origins[0],
                            "localStorage": [
                                {"name": entry[0], "value": entry[1]}
                                for entry in storage["entries"]
                            ],
                        }
                    ],
                }
        except (WebSocketException, OSError, TimeoutError, RuntimeError, ValueError) as failure:
            logger.warning(
                "BOSS context operation failed session=%s stage=%s boundary=%s",
                self.session_id,
                stage,
                type(failure).__name__,
            )
            raise
        finally:
            async with asyncio.timeout(5):
                await cast(Callable[[], Awaitable[None]], cdp.stop)()

    async def _page_snapshot(self, *, conversation_id: str | None = None) -> BossPageSnapshot:
        inventory = await self.client.get("/v1/sessions", follow_redirects=False, timeout=5)
        inventory.raise_for_status()
        active = [
            session
            for session in SessionsResponse.model_validate_json(inventory.content).sessions
            if session.status in {"live", "idle"}
        ]
        if len(active) != 1 or active[0].id != self.session_id or active[0].status != "live":
            raise ValueError("Browser context requires its owned session")
        async with httpx.AsyncClient(base_url=self.cdp_origin, timeout=5) as discovery:
            response = await discovery.get(
                "/json/version", headers={"Host": "localhost"}, follow_redirects=False
            )
            response.raise_for_status()
            discovered = urlsplit(response.json()["webSocketDebuggerUrl"])
        if discovered.scheme not in {"ws", "wss"} or not discovered.path.startswith(
            "/devtools/browser/"
        ):
            raise ValueError("Browser discovery rejected")
        configured = urlsplit(self.cdp_origin)
        endpoint = urlunsplit(
            (
                "wss" if configured.scheme == "https" else "ws",
                configured.netloc,
                discovered.path,
                "",
                "",
            )
        )
        cdp = CDPClient(endpoint)
        try:
            async with asyncio.timeout(20 if conversation_id else 8):
                await cast(Callable[[], Awaitable[None]], cdp.start)()
                targets = await cdp.send.Target.getTargets()
                pages = [target for target in targets["targetInfos"] if target["type"] == "page"]
                if len(pages) != 1:
                    raise ValueError("Browser context requires its owned page")
                page_url = urlsplit(pages[0]["url"])
                if "https://" + str(page_url.hostname) not in BOSS_SCOPE.origins or (
                    page_url.scheme != "https"
                ):
                    raise ValueError("Browser context is outside its site")
                if boss_auth_page_state(pages[0]["url"]) is not None:
                    return BossPageSnapshot(
                        url=urlunsplit((page_url.scheme, page_url.netloc, page_url.path, "", "")),
                        title="",
                        html="",
                    )
                attached = await cdp.send.Target.attachToTarget(
                    params={"targetId": pages[0]["targetId"], "flatten": True}
                )
                if conversation_id is not None:
                    for capture_index in range(6):
                        preview = await cdp.send.Runtime.evaluate(
                            params={
                                "expression": BOSS_RENDERED_CONVERSATIONS,
                                "returnByValue": True,
                            },
                            session_id=attached["sessionId"],
                        )
                        preview_value = preview.get("result", {}).get("value")
                        if preview.get("exceptionDetails") or not isinstance(preview_value, str):
                            raise ValueError("BOSS conversation contract unavailable")
                        previews = parse_boss_rendered_conversations(preview_value)
                        if any(item.conversation_id == conversation_id for item in previews):
                            break
                        if capture_index == 5:
                            raise ValueError("BOSS conversation target unavailable")
                        await asyncio.sleep(1)
                    expression = BOSS_OPEN_CONVERSATION.replace(
                        "__TARGET__", json.dumps(conversation_id)
                    )
                    opened = await cdp.send.Runtime.evaluate(
                        params={"expression": expression, "returnByValue": True},
                        session_id=attached["sessionId"],
                    )
                    if (
                        opened.get("exceptionDetails")
                        or opened.get("result", {}).get("value") is not True
                    ):
                        raise ValueError("BOSS conversation target unavailable")
                    detail_value = "[]"
                    for capture_index in range(8):
                        captured_detail = await cdp.send.Runtime.evaluate(
                            params={
                                "expression": BOSS_RENDERED_MESSAGES.replace(
                                    "__TARGET__", json.dumps(conversation_id)
                                ),
                                "returnByValue": True,
                            },
                            session_id=attached["sessionId"],
                        )
                        detail_value = captured_detail.get("result", {}).get("value")
                        if not isinstance(detail_value, str) or captured_detail.get(
                            "exceptionDetails"
                        ):
                            raise ValueError("BOSS message contract unavailable")
                        if detail_value != "[]" or capture_index == 7:
                            break
                        await asyncio.sleep(1)
                document = await cdp.send.DOM.getDocument(
                    session_id=attached["sessionId"],
                )
                body = await cdp.send.DOM.querySelector(
                    params={"nodeId": document["root"]["nodeId"], "selector": "body"},
                    session_id=attached["sessionId"],
                )
                if body["nodeId"] == 0:
                    raise ValueError("BOSS page snapshot is incomplete")
                captured = await cdp.send.DOM.getOuterHTML(
                    params={"nodeId": body["nodeId"]},
                    session_id=attached["sessionId"],
                )
                conversations: tuple[BossConversationSummary, ...] = ()
                messages: tuple[BossMessageSummary, ...] = ()
                resume_control: BossResumeControl | None = None
                if page_url.path == "/web/geek/chat":
                    rendered = await cdp.send.Runtime.evaluate(
                        params={
                            "expression": BOSS_RENDERED_CONVERSATIONS,
                            "returnByValue": True,
                        },
                        session_id=attached["sessionId"],
                    )
                    value = rendered.get("result", {}).get("value")
                    if not isinstance(value, str) or rendered.get("exceptionDetails"):
                        raise ValueError("BOSS rendered conversation capture is incomplete")
                    conversations = parse_boss_rendered_conversations(value)
                    if conversation_id is not None:
                        messages = parse_boss_rendered_messages(
                            detail_value, conversations, conversation_id
                        )
                        if messages:
                            captured_control = await cdp.send.Runtime.evaluate(
                                params={
                                    "expression": BOSS_RESUME_CONTROL.replace(
                                        "__TARGET__", json.dumps(conversation_id)
                                    ),
                                    "returnByValue": True,
                                },
                                session_id=attached["sessionId"],
                            )
                            control_value = captured_control.get("result", {}).get("value")
                            if not isinstance(control_value, str) or captured_control.get(
                                "exceptionDetails"
                            ):
                                raise ValueError("BOSS resume control unavailable")
                            resume_control = parse_boss_resume_control(
                                control_value, messages, conversation_id
                            )
                current = await cdp.send.Target.getTargetInfo(
                    params={"targetId": pages[0]["targetId"]}
                )
                if current["targetInfo"]["url"] != pages[0]["url"]:
                    raise ValueError("BOSS page changed during capture")
                url = pages[0]["url"]
                title = current["targetInfo"].get("title", "")
                html = captured.get("outerHTML")
                if not isinstance(html, str) or not isinstance(title, str):
                    raise ValueError("BOSS page snapshot is incomplete")
                snapshot_url = urlsplit(url)
                if snapshot_url.scheme != "https" or (
                    "https://" + str(snapshot_url.hostname) not in BOSS_SCOPE.origins
                ):
                    raise ValueError("BOSS page snapshot is outside its site")
                if len(html.encode("utf-8")) > MAX_PAGE_SNAPSHOT_BYTES:
                    logger.warning(
                        "BOSS body exceeds capture bound bytes=%d", len(html.encode("utf-8"))
                    )
                    raise ValueError("BOSS page snapshot is too large")
                return BossPageSnapshot(
                    url=url,
                    title=title,
                    html=html,
                    conversations=conversations,
                    messages=messages,
                    resume_control=resume_control,
                )
        finally:
            try:
                async with asyncio.timeout(5):
                    await cast(Callable[[], Awaitable[None]], cdp.stop)()
            except (WebSocketException, OSError, TimeoutError, RuntimeError):
                raise BossDisconnectUnconfirmed("BOSS executor disconnection unconfirmed") from None


BOSS_RENDERED_CONVERSATIONS = """JSON.stringify((() => {
    const list = document.querySelector('.user-list-content');
    if (list?.__vue__?.$props?.dataKey !== 'uniqueId') return [];
    const normalize = value => typeof value === 'string'
        ? value.replace(/\\s+/g, ' ').trim() : null;
    return Array.from(list.querySelectorAll('.friend-content-warp')).flatMap(row => {
        const component = row.__vue__;
        const source = component?.$props?.source;
        if (component?.$options?.name !== 'boss-item' || !source
            || row.parentElement?.__vue__?.$props?.uniqueKey !== source.uniqueId
            || typeof source.uniqueId !== 'string'
            || !Number.isSafeInteger(source.lastMsgId) || source.lastMsgId <= 0
            || !Number.isSafeInteger(source.unreadCount) || source.unreadCount < 0)
            return [];
        const name = normalize(row.querySelector('.name-text')?.textContent);
        const preview = normalize(row.querySelector('.last-msg-text')?.textContent);
        if (!name || name !== normalize(source.name)
            || preview === null || preview !== normalize(source.lastText)) return [];
        return [{conversation_id: source.uniqueId, recruiter_name: name,
            last_message: preview, last_message_id: String(source.lastMsgId),
            unread: source.unreadCount > 0}];
    });
})())"""

BOSS_OPEN_CONVERSATION = """(() => {
    if (location.origin !== 'https://www.zhipin.com'
        || location.pathname !== '/web/geek/chat') return false;
    const rows = Array.from(document.querySelectorAll('.friend-content-warp')).filter(row =>
        row.__vue__?.$options?.name === 'boss-item'
        && row.__vue__?.$props?.source?.uniqueId === __TARGET__
        && row.parentElement?.__vue__?.$props?.uniqueKey === __TARGET__);
    const target = rows.length === 1 ? rows[0].querySelector('.friend-content') : null;
    if (!target) return false;
    target.click();
    return true;
})()"""

BOSS_RESUME_CONTROL = """JSON.stringify((() => {
    const target = __TARGET__;
    const box = document.querySelector('.chat-conversation');
    const selected = Array.from(document.querySelectorAll('.friend-content-warp'))
        .filter(row => row.querySelector('.friend-content.selected'));
    const source = selected.length === 1 ? selected[0].__vue__?.$props?.source : null;
    if (!source || source.uniqueId !== target
        || box?.__vue__?.$options?.name !== 'conversation-box'
        || box.__vue__.selectedFriend$?.uniqueId !== target
        || !Number.isSafeInteger(source.lastMsgId) || source.lastMsgId <= 0) return null;
    const result = {conversation_id: target, last_message_id: String(source.lastMsgId),
        state: 'unknown', attachment_reported: null, material_state: 'unknown'};
    const toolbars = Array.from(box.querySelectorAll('.chat-editor')).filter(node =>
        node.__vue__?.$options?.name === 'ConversationToolbar');
    const editors = Array.from(box.querySelectorAll('.editor-container')).filter(node =>
        node.__vue__?.$options?.name === 'Editor');
    if (toolbars.length !== 1 || editors.length !== 1
        || editors[0].__vue__.$props?.uniqueId !== target) return result;
    const resumes = Array.from(toolbars[0].querySelectorAll('.toolbar-btn-content'))
        .filter(node => node.__vue__?.$options?.name === 'resumeBtn');
    if (resumes.length !== 1) return result;
    const controls = resumes[0].querySelectorAll('.toolbar-btn');
    if (controls.length !== 1) return result;
    const button = controls[0];
    const disabled = button.classList.contains('unable') || button.hasAttribute('disabled')
        || button.getAttribute('aria-disabled') === 'true';
    if (!disabled && button.getClientRects().length === 0) return result;
    result.state = disabled ? 'unavailable' : 'available';
    const uploads = Array.from(resumes[0].querySelectorAll('*')).filter(node =>
        node.__vue__?.$options?.name === 'choose-upload-resume');
    const hasResume = uploads.length === 1 ? uploads[0].__vue__.$props?.hasResume : null;
    result.attachment_reported = typeof hasResume === 'boolean' ? hasResume : null;
    result.material_state = hasResume === true ? 'present_unidentified'
        : hasResume === false ? 'absent' : 'unknown';
    return result;
})())"""

BOSS_RENDERED_MESSAGES = """JSON.stringify((() => {
    const target = __TARGET__;
    const selected = Array.from(document.querySelectorAll('.friend-content-warp'))
        .filter(row => row.querySelector('.friend-content.selected'));
    const source = selected.length === 1 ? selected[0].__vue__?.$props?.source : null;
    const box = document.querySelector('.chat-conversation');
    if (!source || source.uniqueId !== target || box?.__vue__?.$options?.name !== 'conversation-box'
        || box.__vue__.selectedFriend$?.uniqueId !== target) return [];
    const normalize = value => typeof value === 'string'
        ? value.replace(/\\s+/g, ' ').trim() : null;
    const rows = Array.from(box.querySelectorAll('.im-list > .message-item'));
    if (!rows.length || rows.length > 200) return [];
    const messages = [];
    for (const row of rows) {
        const component = row.__vue__, message = component?.$props?.message;
        const content = row.querySelector('.message-content,.text');
        const contentComponent = content?.__vue__?.$options?.name;
        if (component?.$options?.name !== 'ChatMessage' || !message
            || message.uniqueId !== target || message.friendId !== source.friendId
            || !Number.isSafeInteger(message.mid) || message.mid <= 0
            || component.$vnode?.key !== message.mid
            || !Number.isSafeInteger(message.time) || message.time <= 1e12
            || message.time > Date.now() + 300000
            || typeof message.isSelf !== 'boolean'
            || !['MessageText', 'MessageSystem', 'message-article', 'message-hyperlink']
                .includes(contentComponent)) return [];
        const sender = row.classList.contains('item-system') ? 'system'
            : row.classList.contains('item-myself') && message.isSelf ? 'candidate'
            : row.classList.contains('item-friend') && !message.isSelf ? 'recruiter' : null;
        const textNodes = contentComponent === 'MessageText'
            ? content.querySelectorAll('.text > p > .text-content') : null;
        if (textNodes && textNodes.length !== 1) return [];
        const text = normalize(textNodes ? textNodes[0].textContent : content.textContent);
        if (!sender || !text || text.length > 10000
            || (contentComponent === 'MessageText' && text !== normalize(message.text))) return [];
        let resume_attachment = null;
        if (contentComponent === 'message-hyperlink') {
            const children = Array.from(content.querySelectorAll('*'));
            if (!children.some(node => node.__vue__?.$props?.message === message)) return [];
            const resumes = children.filter(node =>
                node.__vue__?.$options?.name === 'hyperlink-resume');
            if (resumes.length) {
                const link = message.hyperLink;
                const titles = content.querySelectorAll('.message-card-top-title');
                const filename = normalize(link?.text);
                const request = link?.extraJson?.requestDialogMid;
                if (resumes.length !== 1 || resumes[0].__vue__.$props?.message !== message
                    || titles.length !== 1 || !filename || filename.length > 300
                    || /[\\x00-\\x1f\\x7f/\\\\]/.test(filename)
                    || normalize(titles[0].textContent) !== filename
                    || (request != null && request !== 0
                        && (!Number.isSafeInteger(request) || request <= 0))) return [];
                resume_attachment = {filename, sent_by_candidate: message.isSelf,
                    request_message_id: request ? String(request) : null};
            }
        }
        messages.push({conversation_id: target, message_id: String(message.mid), sender,
            content: text, sent_at: new Date(message.time).toISOString(), resume_attachment});
    }
    if (messages.at(-1)?.message_id !== String(source.lastMsgId)
        || box.__vue__.selectedFriend$?.uniqueId !== target) return [];
    return messages;
})())"""
