from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import httpx
import pytest
from pydantic import AnyHttpUrl

from services.browser.site_adapters.boss_context import (
    MAX_PAGE_SNAPSHOT_BYTES,
    BossContextReader,
    BossContextUnavailable,
    BossPageSnapshot,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [None, "owner", "multiple", "site", "cookie_only", "verify", "anonymous", "storage_timeout"],
)
async def test_context_capture_is_scoped_disconnects_and_uses_no_runtime_enable(
    monkeypatch: pytest.MonkeyPatch, changed: str | None
) -> None:
    session_id = uuid4()
    target = {
        "type": "page",
        "targetId": "owned",
        "url": "https://example.com"
        if changed == "site"
        else "https://www.zhipin.com/web/passport/zp/verify.html"
        if changed == "verify"
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
                getDOMStorageItems=AsyncMock(
                    side_effect=TimeoutError if changed == "storage_timeout" else None,
                    return_value={"entries": [["synthetic", "value"]]},
                )
            ),
            DOM=SimpleNamespace(
                getDocument=AsyncMock(return_value={"root": {"nodeId": 1}}),
                querySelector=AsyncMock(
                    return_value={"nodeId": 0 if changed == "anonymous" else 2}
                ),
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
            assert state["authenticated"] is (changed not in {"verify", "anonymous"})
            if changed == "storage_timeout":
                assert state["origins"][0]["localStorage"] == []
    if changed != "owner":
        cdp.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_page_observation_waits_for_structure_without_replaying_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = BossContextReader(AsyncMock(), AnyHttpUrl("http://cdp"), uuid4())
    page = "https://www.zhipin.com/web/geek/chat"
    snapshots = AsyncMock(
        side_effect=[
            BossPageSnapshot(page, "Synthetic BOSS", "<main>正在加载</main>"),
            BossPageSnapshot(
                page,
                "Synthetic BOSS",
                '<main><div data-message-id="m1">Synthetic message</div></main>',
            ),
        ]
    )
    monkeypatch.setattr(reader, "page_snapshot", snapshots)
    pause = AsyncMock()
    monkeypatch.setattr("services.browser.site_adapters.boss_context.asyncio.sleep", pause)
    observed = await reader.read_page()
    assert observed.state == "ready" and observed.messages[0].message_id == "m1"
    assert snapshots.await_count == 2
    pause.assert_awaited_once_with(1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        None,
        "owner",
        "multiple",
        "site",
        "login",
        "verify",
        "navigation",
        "oversize",
        "malformed",
        "rendered",
        "rendered_invalid",
        "rendered_exception",
        "rendered_timeout",
        "conversation",
        "conversation_pending",
        "conversation_missing",
        "observe_only",
        "observe_wrong_thread",
        "disconnect",
    ],
)
async def test_page_snapshot_is_read_only_scoped_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
    changed: str | None,
) -> None:
    session_id = uuid4()
    target = {
        "type": "page",
        "targetId": "owned",
        "url": "https://example.com"
        if changed == "site"
        else (
            "https://www.zhipin.com/web/user/?credential=synthetic#private"
            if changed == "login"
            else "https://www.zhipin.com/web/passport/zp/verify.html?token=synthetic"
            if changed == "verify"
            else "https://www.zhipin.com/web/geek/chat"
        ),
    }
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
                getTargetInfo=AsyncMock(
                    return_value={
                        "targetInfo": target
                        | {
                            "title": "BOSS直聘",
                            "url": "https://example.com"
                            if changed == "navigation"
                            else target["url"],
                        }
                    }
                ),
                attachToTarget=AsyncMock(return_value={"sessionId": "owned-attachment"}),
            ),
            DOM=SimpleNamespace(
                getDocument=AsyncMock(return_value={"root": {"nodeId": 1}}),
                querySelector=AsyncMock(return_value={"nodeId": 2}),
                getOuterHTML=AsyncMock(
                    return_value={
                        "outerHTML": (
                            "x" * (MAX_PAGE_SNAPSHOT_BYTES + 1)
                            if changed == "oversize"
                            else None
                            if changed == "malformed"
                            else "<main data-page='chat'></main>"
                        )
                    }
                ),
            ),
            Runtime=SimpleNamespace(
                evaluate=AsyncMock(
                    side_effect=TimeoutError if changed == "rendered_timeout" else None,
                    return_value={
                        "result": {
                            "value": "invalid"
                            if changed == "rendered_invalid"
                            else '[{"conversation_id":"thread-1","recruiter_name":"Synthetic HR",'
                            '"last_message":"Synthetic preview",'
                            '"last_message_id":"123","unread":true}]'
                            if changed == "rendered"
                            else "[]"
                        },
                        **(
                            {"exceptionDetails": {"text": "private"}}
                            if changed == "rendered_exception"
                            else {}
                        ),
                    },
                )
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

    reader = BossContextReader(client, AnyHttpUrl("http://cdp"), session_id)
    if changed in {
        "conversation",
        "conversation_pending",
        "conversation_missing",
        "disconnect",
        "observe_only",
        "observe_wrong_thread",
    }:
        from services.browser.site_adapters.boss_context import (
            BOSS_MESSAGE_DIAGNOSTIC,
            BOSS_OPEN_CONVERSATION,
            BOSS_RENDERED_CONVERSATIONS,
            BOSS_RESUME_CONTROL,
            BossDisconnectUnconfirmed,
        )

        preview = (
            '[{"conversation_id":"thread-1","recruiter_name":"Synthetic HR",'
            '"last_message":"Synthetic preview","last_message_id":"123","unread":true}]'
        )
        detail = (
            '[{"conversation_id":"thread-1","message_id":"123","sender":"recruiter",'
            '"content":"Synthetic detail","sent_at":"2026-10-12T00:00:00.000Z"}]'
        )
        clicks = 0
        captures = 0

        async def evaluate(*, params: dict[str, object], session_id: str) -> object:
            nonlocal clicks, captures
            expression = params["expression"]
            if expression == BOSS_RENDERED_CONVERSATIONS:
                value: object = "[]" if changed == "conversation_missing" else preview
            elif expression == BOSS_RESUME_CONTROL.replace("__TARGET__", '"thread-1"'):
                value = (
                    '{"conversation_id":"thread-1","last_message_id":"123",'
                    '"state":"unavailable","attachment_reported":false,'
                    '"material_state":"absent"}'
                )
            elif expression == BOSS_OPEN_CONVERSATION.replace("__TARGET__", '"thread-1"'):
                clicks += 1
                value = True
            elif expression == BOSS_MESSAGE_DIAGNOSTIC.replace("__TARGET__", '"thread-1"'):
                value = "selection"
            else:
                captures += 1
                value = (
                    "[]"
                    if (
                        changed == "conversation_pending"
                        and captures == 1
                        or changed == "observe_wrong_thread"
                    )
                    else detail
                )
            return {"result": {"value": value}}

        cdp.send.Runtime.evaluate.side_effect = evaluate
        cdp.send.DOM.getOuterHTML.return_value = {
            "outerHTML": '<main class="chat-container"><div class="chat-content"></div>'
            '<div class="chat-conversation"></div><div class="chat-user"></div></main>'
        }
        monkeypatch.setattr(
            "services.browser.site_adapters.boss_context.asyncio.sleep", AsyncMock()
        )
        if changed == "disconnect":
            cdp.stop.side_effect = TimeoutError
        if changed in {"conversation_missing", "disconnect"}:
            with pytest.raises(
                BossDisconnectUnconfirmed if changed == "disconnect" else BossContextUnavailable
            ):
                await reader.read_conversation("thread-1")
        else:
            page = await reader.read_conversation(
                "thread-1", navigate=changed not in {"observe_only", "observe_wrong_thread"}
            )
            if changed == "observe_wrong_thread":
                assert page.messages == () and page.resume_control is None
            else:
                assert page.messages[0].message_id == "123"
                assert page.resume_control is not None
                assert page.resume_control.state == "unavailable"
        assert clicks == (
            0 if changed in {"conversation_missing", "observe_only", "observe_wrong_thread"} else 1
        )
        assert captures == (
            8
            if changed == "observe_wrong_thread"
            else 2
            if changed == "conversation_pending"
            else 0
            if changed == "conversation_missing"
            else 1
        )
        cdp.stop.assert_awaited_once()
        return
    if changed is not None and changed not in {"login", "verify", "rendered"}:
        with pytest.raises(BossContextUnavailable):
            await reader.page_snapshot()
    elif changed in {"login", "verify"}:
        snapshot = await reader.page_snapshot()
        assert "?" not in snapshot.url and "#" not in snapshot.url
        assert snapshot.html == "" and snapshot.title == ""
        cdp.send.Target.attachToTarget.assert_not_awaited()
        cdp.send.DOM.getDocument.assert_not_awaited()
        cdp.send.DOM.getOuterHTML.assert_not_awaited()
        cdp.send.Runtime.evaluate.assert_not_awaited()
    else:
        snapshot = await reader.page_snapshot()
        assert snapshot.url.endswith("/web/geek/chat")
        assert snapshot.title == "BOSS直聘"
        assert snapshot.html == "<main data-page='chat'></main>"
        assert snapshot.html not in repr(snapshot)
        if changed == "rendered":
            assert snapshot.conversations[0].conversation_id == "thread-1"
            assert snapshot.conversations[0].last_message_id == "123"
        else:
            assert snapshot.conversations == ()
        cdp.send.DOM.getOuterHTML.assert_awaited_once_with(
            params={"nodeId": 2}, session_id="owned-attachment"
        )
    if changed in {"owner", "multiple", "site"}:
        cdp.send.DOM.getOuterHTML.assert_not_awaited()
        cdp.send.Runtime.evaluate.assert_not_awaited()
    if changed != "owner":
        cdp.stop.assert_awaited_once()
