import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import cast
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
from cdp_use import CDPClient
from pydantic import AnyHttpUrl
from websockets.exceptions import WebSocketException

from services.browser.sessions.viewer import ViewerRejected, resolve_viewer_page

BOSS_LOGIN_URL = "https://www.zhipin.com/web/user/"


class BossLoginUnavailable(Exception):
    pass


class BossLoginNavigator:
    def __init__(self, steel_client: httpx.AsyncClient, cdp_origin: AnyHttpUrl) -> None:
        self.steel_client = steel_client
        self.cdp_origin = str(cdp_origin).rstrip("/")

    async def __call__(self, session_id: UUID) -> None:
        try:
            page_id = await resolve_viewer_page(self.steel_client, session_id, None)
            async with httpx.AsyncClient(base_url=self.cdp_origin, timeout=5) as client:
                response = await client.get(
                    "/json/version", headers={"Host": "localhost"}, follow_redirects=False
                )
                response.raise_for_status()
                discovered = urlsplit(response.json()["webSocketDebuggerUrl"])
            if discovered.scheme not in {"ws", "wss"} or not discovered.path.startswith(
                "/devtools/browser/"
            ):
                raise BossLoginUnavailable("Login browser discovery rejected")
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
            cdp_client = CDPClient(endpoint)
            try:
                async with asyncio.timeout(5):
                    await cast(Callable[[], Awaitable[None]], cdp_client.start)()
                    targets = await cdp_client.send.Target.getTargets()
                pages = [target for target in targets["targetInfos"] if target["type"] == "page"]
                if len(pages) != 1 or pages[0]["targetId"] != page_id:
                    raise BossLoginUnavailable("Login browser requires its owned page")
                if pages[0]["url"] != "about:blank":
                    raise BossLoginUnavailable("Login browser page changed")
                async with asyncio.timeout(20):
                    attached = await cdp_client.send.Target.attachToTarget(
                        params={"targetId": page_id, "flatten": True}
                    )
                    result = await cdp_client.send.Page.navigate(
                        params={"url": BOSS_LOGIN_URL, "transitionType": "address_bar"},
                        session_id=attached["sessionId"],
                    )
                if result.get("errorText"):
                    raise BossLoginUnavailable("Login browser navigation failed")
                deadline = monotonic() + 3
                retained_site = False
                async with asyncio.timeout(5):
                    while True:
                        info = await cdp_client.send.Target.getTargetInfo(
                            params={"targetId": page_id}
                        )
                        current = urlsplit(info["targetInfo"]["url"])
                        if current.scheme == "https" and current.hostname == "www.zhipin.com":
                            retained_site = True
                        elif info["targetInfo"]["url"] in {"", "about:blank"}:
                            retained_site = False
                        else:
                            raise BossLoginUnavailable(
                                "Login browser did not retain the site: "
                                + str(current.scheme)
                                + "://"
                                + str(current.hostname)
                            )
                        if monotonic() >= deadline:
                            if not retained_site:
                                raise BossLoginUnavailable("Login browser did not load the site")
                            break
                        await asyncio.sleep(0.25)
            finally:
                try:
                    async with asyncio.timeout(5):
                        await cast(Callable[[], Awaitable[None]], cdp_client.stop)()
                except (OSError, WebSocketException, TimeoutError):
                    raise BossLoginUnavailable("Login browser disconnect unconfirmed") from None
        except (
            httpx.HTTPError,
            WebSocketException,
            OSError,
            TimeoutError,
            RuntimeError,
            ViewerRejected,
            ValueError,
            KeyError,
            TypeError,
        ):
            raise BossLoginUnavailable("Login browser navigation unavailable") from None
