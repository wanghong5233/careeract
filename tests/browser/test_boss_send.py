import json
import shutil
import subprocess
from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from services.browser.site_adapters.boss import BossConversationSummary, BossMessageSummary
from services.browser.site_adapters.boss_context import BossContextReader, BossPageSnapshot
from services.browser.site_adapters.boss_controls import BOSS_TEXT_CONTROL
from services.browser.site_adapters.boss_send import (
    BossSendIntent,
    send_boss_text,
)


@pytest.mark.parametrize(
    "changed", [None, "target", "editor", "duplicate", "hidden", "draft", "disabled", "input"]
)
def test_semantic_send_control_uses_one_owned_visible_editor(changed: str | None) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node runtime unavailable")
    fixture = """
const target = 'thread-1', source = {uniqueId: target};
const input = {innerText: changed === 'draft' ? 'Human draft' : '',
    getClientRects: () => changed === 'hidden' ? [] : [1]};
const button = {textContent: '发送', children: [], getClientRects: () => [1],
    closest: () => changed === 'disabled' ? {} : null};
const editor = {__vue__: {$options: {name: 'Editor'}, $props: {uniqueId: target}},
    querySelectorAll: selector => selector === '*' ? changed === 'duplicate'
        ? [button, button] : [button] : changed === 'input' ? [input,input] : [input]};
const box = {__vue__: {$options: {name: 'conversation-box'}, selectedFriend$: source},
    querySelectorAll: () => [editor]};
const selected = {__vue__: {$props: {source}}, querySelector: () => ({})};
const document = {querySelector: () => box, querySelectorAll: () => [selected]};
if (changed === 'target') box.__vue__.selectedFriend$ = {uniqueId: 'other'};
if (changed === 'editor') editor.__vue__.$props.uniqueId = 'other';
"""
    script = "const changed=" + json.dumps(changed) + ";" + fixture
    script += "const control=" + BOSS_TEXT_CONTROL.replace("__TARGET__", json.dumps("thread-1"))
    script += ";process.stdout.write(JSON.stringify(control && "
    script += "{disabled:control.disabled,text:control.text}));"
    observed = json.loads(
        subprocess.run(
            [node, "-"], input=script, text=True, capture_output=True, check=True, timeout=5
        ).stdout
    )
    if changed in {"target", "editor", "duplicate", "hidden", "input"}:
        assert observed is None
    else:
        assert observed == {
            "disabled": changed == "disabled",
            "text": "Human draft" if changed == "draft" else "",
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        None,
        "context_card",
        "anchor_changed",
        "source",
        "candidate",
        "target",
        "draft",
        "focus",
        "click",
        "transport",
        "evidence",
    ],
)
async def test_send_preflight_and_delivery_evidence_never_replay_input(changed: str | None) -> None:
    message = BossMessageSummary("123", "recruiter", "Incoming", None, "thread-1")
    if changed == "source":
        message = replace(message, content="Changed incoming")
    if changed == "candidate":
        message = replace(message, sender="candidate")
    if changed == "target":
        message = replace(message, conversation_id="other")
    snapshot = BossPageSnapshot(
        "https://www.zhipin.com/web/geek/chat",
        "",
        "",
        conversations=(
            BossConversationSummary(
                "thread-1",
                "Synthetic",
                None,
                None,
                None,
                False,
                None,
                "999" if changed == "anchor_changed" else "123",
            ),
        ),
        messages=(
            message,
            BossMessageSummary("125", "recruiter", "Information card", None, "thread-1"),
        )
        if changed == "context_card"
        else (message,),
    )
    conversations = json.dumps(
        [
            {
                "conversation_id": "thread-1",
                "recruiter_name": "Synthetic",
                "last_message": "Reply",
                "last_message_id": "124",
                "unread": False,
            }
        ]
    )
    detail = json.dumps(
        [
            {
                "conversation_id": "thread-1",
                "message_id": "123",
                "sender": "recruiter",
                "content": "Incoming",
                "sent_at": "2026-10-14T01:00:00.000Z",
            },
            {
                "conversation_id": "thread-1",
                "message_id": "124",
                "sender": "candidate",
                "content": "Other" if changed == "evidence" else "Reply",
                "sent_at": "2026-10-14T01:00:01.000Z",
            },
        ]
    )
    values: list[object] = [changed != "draft", changed != "focus", changed != "click"]
    values += [value for _ in range(6) for value in (conversations, detail)]
    evaluate = AsyncMock(side_effect=[{"result": {"value": v}} for v in values])
    insert = AsyncMock(
        side_effect=TimeoutError("Synthetic transport loss") if changed == "transport" else None
    )
    cdp = SimpleNamespace(
        send=SimpleNamespace(
            Runtime=SimpleNamespace(evaluate=evaluate), Input=SimpleNamespace(insertText=insert)
        )
    )
    reader = AsyncMock()

    async def page_snapshot(**options: object) -> BossPageSnapshot:
        from collections.abc import Awaitable, Callable

        operation = cast(Callable[..., Awaitable[None]], options["operation"])
        await operation(cdp, "owned-session", snapshot)
        return snapshot

    reader._page_snapshot.side_effect = page_snapshot
    mark = AsyncMock()
    if changed == "transport":
        with pytest.raises(TimeoutError):
            await send_boss_text(
                cast(BossContextReader, reader),
                BossSendIntent("thread-1", "123", "Incoming", "Reply"),
                mark,
            )
    else:
        result = await send_boss_text(
            cast(BossContextReader, reader),
            BossSendIntent("thread-1", "123", "Incoming", "Reply"),
            mark,
        )
        expected = (
            "completed"
            if changed in {None, "context_card"}
            else "failed"
            if changed in {"source", "candidate", "target", "draft", "anchor_changed"}
            else "unknown"
        )
        assert result.state == expected
        assert result.message_id == ("124" if changed in {None, "context_card"} else None)
    assert insert.await_count <= 1 and mark.await_count <= 1
    if changed in {"source", "candidate", "target", "draft", "anchor_changed"}:
        assert mark.await_count == insert.await_count == 0
    if changed in {None, "context_card"}:
        expressions = [call.kwargs["params"]["expression"] for call in evaluate.await_args_list]
        assert sum("c.button.click()" in e for e in expressions) == 1
