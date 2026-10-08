from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import httpx
import pytest
from pydantic import AnyHttpUrl

from services.browser.site_adapters.boss_context import BossContextReader, BossContextUnavailable


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [None, "owner", "multiple", "site", "cookie_only"])
async def test_context_capture_is_scoped_disconnects_and_uses_no_runtime_enable(
    monkeypatch: pytest.MonkeyPatch, changed: str | None
) -> None:
    session_id = uuid4()
    target = {
        "type": "page",
        "targetId": "owned",
        "url": "https://example.com"
        if changed == "site"
        else "https://www.zhipin.com/web/geek/jobs",
    }
    cookies = [{"name": "synthetic", "value": "synthetic", "domain": ".zhipin.com"}]
    cdp = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        send=SimpleNamespace(
            Target=SimpleNamespace(
                getTargets=AsyncMock(
                    return_value={
                        "targetInfos": [target, target] if changed == "multiple" else [target]
                    }
                ),
                attachToTarget=AsyncMock(return_value={"sessionId": "owned-attachment"}),
            ),
            Network=SimpleNamespace(getAllCookies=AsyncMock(return_value={"cookies": cookies})),
            DOMStorage=SimpleNamespace(
                getDOMStorageItems=AsyncMock(return_value={"entries": [["synthetic", "value"]]})
            ),
            DOM=SimpleNamespace(
                getDocument=AsyncMock(return_value={"root": {"nodeId": 1}}),
                querySelector=AsyncMock(return_value={"nodeId": 2}),
            ),
        ),
    )
    monkeypatch.setattr(
        "services.browser.site_adapters.boss_context.CDPClient", Mock(return_value=cdp)
    )
    discovery = AsyncMock()
    discovery.get.return_value = httpx.Response(
        200,
        json={"webSocketDebuggerUrl": "ws://internal/devtools/browser/owned"},
        request=httpx.Request("GET", "http://cdp/json/version"),
    )
    monkeypatch.setattr(
        "services.browser.site_adapters.boss_context.httpx.AsyncClient",
        Mock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=discovery), __aexit__=AsyncMock()
            )
        ),
    )
    client = AsyncMock()
    client.get.return_value = httpx.Response(
        200,
        json={
            "sessions": [
                {"id": str(uuid4() if changed == "owner" else session_id), "status": "live"}
            ]
        },
        request=httpx.Request("GET", "http://steel/v1/sessions"),
    )
    reader = BossContextReader(
        client,
        AnyHttpUrl("http://cdp"),
        session_id,
        include_local_storage=changed != "cookie_only",
    )
    if changed in {"owner", "multiple", "site"}:
        with pytest.raises(BossContextUnavailable):
            await reader.storage_state()
        cdp.send.Network.getAllCookies.assert_not_awaited()
    else:
        state = await reader.storage_state()
        assert isinstance(state, dict) and state["cookies"] == cookies
        if changed == "cookie_only":
            assert state["origins"] == []
            cdp.send.DOMStorage.getDOMStorageItems.assert_not_awaited()
        else:
            assert state["origins"][0]["origin"] == "https://www.zhipin.com"
    if changed != "owner":
        cdp.stop.assert_awaited_once()
