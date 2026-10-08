from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from pydantic import AnyHttpUrl

from services.browser.site_adapters.boss_login import (
    BOSS_LOGIN_URL,
    BossLoginNavigator,
    BossLoginUnavailable,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [None, "target", "url", "multiple_pages", "discovery"])
async def test_login_navigation_uses_owned_blank_page_and_disconnects(
    monkeypatch: pytest.MonkeyPatch, changed: str | None
) -> None:
    session_id = uuid4()
    page_id = "owned-page"
    target = AsyncMock()
    target.send.return_value = {
        "targetInfo": {"targetId": "other" if changed == "target" else page_id}
    }
    page = SimpleNamespace(
        url="https://example.com" if changed == "url" else "about:blank",
        goto=AsyncMock(),
        context=SimpleNamespace(new_cdp_session=AsyncMock(return_value=target)),
    )
    browser = SimpleNamespace(
        contexts=[SimpleNamespace(pages=[page, page] if changed == "multiple_pages" else [page])],
        close=AsyncMock(),
    )
    connect = AsyncMock(return_value=browser)

    @asynccontextmanager
    async def playwright() -> AsyncIterator[SimpleNamespace]:
        yield SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=connect))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/sessions":
            return httpx.Response(
                200, json={"sessions": [{"id": str(session_id), "status": "live"}]}
            )
        if request.url.path.endswith("/live-details"):
            return httpx.Response(200, json={"pages": [{"id": page_id}]})
        assert request.url.path == "/json/version"
        return httpx.Response(
            200,
            json={
                "webSocketDebuggerUrl": "ws://internal:9223/"
                + ("unexpected" if changed == "discovery" else "devtools/browser/synthetic")
            },
        )

    monkeypatch.setattr("services.browser.site_adapters.boss_login.async_playwright", playwright)
    cdp_client = httpx.AsyncClient(
        base_url="http://cdp:9223", transport=httpx.MockTransport(handler)
    )
    steel_client = httpx.AsyncClient(
        base_url="http://steel", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(
        "services.browser.site_adapters.boss_login.httpx.AsyncClient", Mock(return_value=cdp_client)
    )
    async with steel_client:
        navigator = BossLoginNavigator(steel_client, AnyHttpUrl("http://cdp:9223"))
        if changed is None:
            await navigator(session_id)
            page.goto.assert_awaited_once_with(
                BOSS_LOGIN_URL, wait_until="domcontentloaded", timeout=20000
            )
        else:
            with pytest.raises(BossLoginUnavailable):
                await navigator(session_id)
            page.goto.assert_not_awaited()
    if changed == "discovery":
        connect.assert_not_awaited()
    else:
        browser.close.assert_awaited_once()
