import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
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
    BossPageState,
    BossReadOnlyPage,
    boss_auth_page_state,
    parse_boss_page,
    parse_boss_rendered_conversations,
)

BOSS_SCOPE = SiteScope("boss", ("https://www.zhipin.com",), ("zhipin.com", "www.zhipin.com"))
MAX_PAGE_SNAPSHOT_BYTES = 4 * 1024 * 1024
logger = logging.getLogger(__name__)


class BossContextUnavailable(Exception):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class BossPageSnapshot:
    url: str
    title: str
    html: str
    conversations: tuple[BossConversationSummary, ...] = ()


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

    async def _page_snapshot(self) -> BossPageSnapshot:
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
            async with asyncio.timeout(8):
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
                    url=url, title=title, html=html, conversations=conversations
                )
        finally:
            async with asyncio.timeout(5):
                await cast(Callable[[], Awaitable[None]], cdp.stop)()


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
