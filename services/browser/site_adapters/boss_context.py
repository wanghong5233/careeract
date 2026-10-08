import asyncio
from collections.abc import Awaitable, Callable
from typing import cast
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
from cdp_use import CDPClient
from pydantic import AnyHttpUrl
from websockets.exceptions import WebSocketException

from services.browser.sessions.context import SiteScope
from services.browser.sessions.steel import SessionsResponse

BOSS_SCOPE = SiteScope("boss", ("https://www.zhipin.com",), ("zhipin.com", "www.zhipin.com"))


class BossContextUnavailable(Exception):
    pass


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
        ):
            raise BossContextUnavailable("BOSS context capture unavailable") from None

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
        try:
            async with asyncio.timeout(8):
                await cast(Callable[[], Awaitable[None]], cdp.start)()
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
                cookies = await cdp.send.Network.getAllCookies(session_id=attached["sessionId"])
                if not self.include_local_storage:
                    return {"cookies": cookies["cookies"], "origins": []}
                storage = await cdp.send.DOMStorage.getDOMStorageItems(
                    params={
                        "storageId": {
                            "securityOrigin": BOSS_SCOPE.origins[0],
                            "isLocalStorage": True,
                        }
                    },
                    session_id=attached["sessionId"],
                )
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
        finally:
            async with asyncio.timeout(5):
                await cast(Callable[[], Awaitable[None]], cdp.stop)()
