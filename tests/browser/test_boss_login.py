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
@pytest.mark.parametrize(
    "changed",
    [
        None,
        "initial_blank",
        "initial_empty",
        "redirect_blank",
        "redirect_empty",
        "target",
        "url",
        "multiple_pages",
        "discovery",
        "navigation",
        "blank",
        "empty",
        "foreign",
    ],
)
async def test_login_navigation_uses_owned_blank_page_and_disconnects(
    monkeypatch: pytest.MonkeyPatch, changed: str | None
) -> None:
    session_id = uuid4()
    page_id = "owned-page"
    target = {
        "targetId": "other" if changed == "target" else page_id,
        "url": "https://example.com" if changed == "url" else "about:blank",
        "type": "page",
    }
    navigation = AsyncMock(return_value={"errorText": "private"} if changed == "navigation" else {})
    retained_url = (
        ""
        if changed == "empty"
        else "about:blank"
        if changed == "blank"
        else "https://example.com"
        if changed == "foreign"
        else BOSS_LOGIN_URL
    )
    client = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        send=SimpleNamespace(
            Target=SimpleNamespace(
                getTargets=AsyncMock(
                    return_value={
                        "targetInfos": [target, target] if changed == "multiple_pages" else [target]
                    }
                ),
                attachToTarget=AsyncMock(return_value={"sessionId": "owned-attachment"}),
                getTargetInfo=AsyncMock(return_value={"targetInfo": {"url": retained_url}}),
            ),
            Page=SimpleNamespace(navigate=navigation),
        ),
    )
    constructor = Mock(return_value=client)
    if changed in {"initial_blank", "initial_empty"}:
        client.send.Target.getTargetInfo.side_effect = [
            {"targetInfo": {"url": "" if changed == "initial_empty" else "about:blank"}},
            {"targetInfo": {"url": BOSS_LOGIN_URL}},
        ]
    if changed in {"redirect_blank", "redirect_empty"}:
        client.send.Target.getTargetInfo.side_effect = [
            {"targetInfo": {"url": BOSS_LOGIN_URL}},
            {"targetInfo": {"url": "" if changed == "redirect_empty" else "about:blank"}},
            {"targetInfo": {"url": "https://www.zhipin.com/"}},
        ]

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

    monkeypatch.setattr("services.browser.site_adapters.boss_login.CDPClient", constructor)
    monkeypatch.setattr(
        "services.browser.site_adapters.boss_login.monotonic",
        Mock(
            side_effect=[0, 0, 1, 4]
            if changed in {"redirect_blank", "redirect_empty"}
            else [0, 0, 4]
            if changed in {"initial_blank", "initial_empty"}
            else [0, 4]
        ),
    )
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
        if changed in {None, "initial_blank", "initial_empty", "redirect_blank", "redirect_empty"}:
            await navigator(session_id)
            constructor.assert_called_once_with("ws://cdp:9223/devtools/browser/synthetic")
            navigation.assert_awaited_once_with(
                params={"url": BOSS_LOGIN_URL, "transitionType": "address_bar"},
                session_id="owned-attachment",
            )
        else:
            with pytest.raises(BossLoginUnavailable):
                await navigator(session_id)
            if changed not in {"navigation", "blank", "empty", "foreign"}:
                navigation.assert_not_awaited()
    if changed == "discovery":
        constructor.assert_not_called()
    else:
        client.stop.assert_awaited_once()
