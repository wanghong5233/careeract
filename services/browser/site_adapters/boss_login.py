from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright
from pydantic import AnyHttpUrl

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
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(
                    endpoint, headers={"Host": "localhost"}, timeout=5000
                )
                try:
                    pages = [page for context in browser.contexts for page in context.pages]
                    if len(pages) != 1:
                        raise BossLoginUnavailable("Login browser requires one page")
                    page = pages[0]
                    target = await page.context.new_cdp_session(page)
                    try:
                        info = await target.send("Target.getTargetInfo")
                    finally:
                        await target.detach()
                    if info["targetInfo"]["targetId"] != page_id or page.url != "about:blank":
                        raise BossLoginUnavailable("Login browser page changed")
                    await page.goto(BOSS_LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
                finally:
                    await browser.close()
        except (httpx.HTTPError, PlaywrightError, ViewerRejected, ValueError, KeyError, TypeError):
            raise BossLoginUnavailable("Login browser navigation unavailable") from None
