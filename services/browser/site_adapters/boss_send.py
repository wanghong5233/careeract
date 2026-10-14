import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from cdp_use import CDPClient

from services.browser.site_adapters.boss import (
    parse_boss_rendered_conversations,
    parse_boss_rendered_messages,
)
from services.browser.site_adapters.boss_context import (
    BOSS_MESSAGE_CAPTURE,
    BOSS_RENDERED_CONVERSATIONS,
    BOSS_RENDERED_MESSAGES,
    BossContextReader,
    BossPageSnapshot,
)
from services.browser.site_adapters.boss_controls import BOSS_TEXT_CONTROL


@dataclass(frozen=True, slots=True, repr=False)
class BossSendIntent:
    conversation_id: str
    message_id: str
    source_text: str
    text: str


@dataclass(frozen=True, slots=True)
class BossSendResult:
    state: str
    message_id: str | None = None


async def send_boss_text(
    reader: BossContextReader, intent: BossSendIntent, mark_attempt: Callable[[], Awaitable[None]]
) -> BossSendResult:
    result = BossSendResult("failed")

    async def operation(cdp: CDPClient, session: str, snapshot: BossPageSnapshot) -> None:
        nonlocal result
        targets = [c for c in snapshot.conversations if c.conversation_id == intent.conversation_id]
        if len(targets) != 1 or targets[0].last_message_id != intent.message_id:
            return
        anchor = next(
            (i for i, m in enumerate(snapshot.messages) if m.message_id == intent.message_id),
            None,
        )
        if anchor is None:
            return
        human = [
            m for m in snapshot.messages[: anchor + 1] if m.sender in {"candidate", "recruiter"}
        ]
        if (
            not human
            or human[-1].sender != "recruiter"
            or human[-1].message_id != intent.message_id
            or human[-1].content != intent.source_text
            or any(m.conversation_id != intent.conversation_id for m in snapshot.messages)
        ):
            return
        control = BOSS_TEXT_CONTROL.replace("__TARGET__", json.dumps(intent.conversation_id))

        async def evaluate(expression: str) -> object:
            response = await cdp.send.Runtime.evaluate(
                params={"expression": expression, "returnByValue": True}, session_id=session
            )
            if response.get("exceptionDetails"):
                raise ValueError("BOSS text control unavailable")
            return response.get("result", {}).get("value")

        clean = await evaluate(f"(() => {{const c={control};return !!c && !c.text;}})()")
        if clean is not True:
            return
        # Persist before the first edit/click; crash or transport loss is never replayed.
        await mark_attempt()
        result = BossSendResult("unknown")
        focused = await evaluate(
            f"(() => {{const c={control};if (!c || c.text) return false;"
            "c.input.focus();return document.activeElement===c.input;})()"
        )
        if focused is not True:
            return
        await cdp.send.Input.insertText(params={"text": intent.text}, session_id=session)
        messages_before_click = BOSS_MESSAGE_CAPTURE.replace(
            "__TARGET__", json.dumps(intent.conversation_id)
        )
        clicked = await evaluate(
            f"(() => {{const capture={messages_before_click};"
            "const latest=capture.messages.find(m=>m.message_id===capture.latest_message_id);"
            f"if (capture.reason!=='ready' || latest?.message_id!=={json.dumps(intent.message_id)} "
            f"|| latest.sender!=='recruiter' || latest.content!=={json.dumps(intent.source_text)}) "
            f"return false;const c={control};if (!c || c.disabled || "
            f"c.text!=={json.dumps(intent.text.strip())}) return false;"
            "c.button.click();return true;})()"
        )
        if clicked is not True:
            return
        before = {m.message_id for m in snapshot.messages}
        for index in range(6):
            preview = await evaluate(BOSS_RENDERED_CONVERSATIONS)
            detail = await evaluate(
                BOSS_RENDERED_MESSAGES.replace("__TARGET__", json.dumps(intent.conversation_id))
            )
            if not isinstance(preview, str) or not isinstance(detail, str):
                return
            messages = parse_boss_rendered_messages(
                detail, parse_boss_rendered_conversations(preview), intent.conversation_id
            )
            added = [
                m
                for m in messages
                if m.message_id not in before
                and m.sender == "candidate"
                and m.content == " ".join(intent.text.split())
            ]
            if len(added) == 1:
                result = BossSendResult("completed", added[0].message_id)
                return
            if len(added) > 1:
                return
            if index != 5:
                await asyncio.sleep(0.5)

    await reader._page_snapshot(conversation_id=intent.conversation_id, operation=operation)
    return result
