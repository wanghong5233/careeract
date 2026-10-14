"""Opt-in real Patchright input on synthetic pages and isolated PostgreSQL.

NORMAL_INPUT_CDP_URL selects an isolated Steel canary. Without it this uses installed
Edge. No real account/site is accessed. Fixture scripts are local test page behavior.
"""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import pytest
from fastapi import WebSocket
from patchright.async_api import Page
from patchright.async_api import async_playwright as async_patchright
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from websockets.asyncio.client import connect

from scripts.smoke_steel_viewer import receive_frame
from services.browser.app.factory import _relay_websocket
from services.browser.sessions.authentication import BrowserCommand, CommandRejected
from services.browser.sessions.lease import LeaseConflict
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.sessions.ui_input import NormalUIInput, UIInputRejected, UIInputUncertain
from services.browser.sessions.viewer import ViewerRejected
from tests.browser.test_command_authentication import command_payload
from tests.browser.test_postgres_leases import database_url as database_url

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_NORMAL_INPUT_TESTS") != "1",
    reason="Opt-in synthetic Patchright/isolated PostgreSQL acceptance",
)
URL = "http://careeract.local.test/form"
FORM = """<!doctype html><meta charset="utf-8"><title>CareerAct normal input canary</title>
<style>body {font:20px sans-serif;padding:24px} input,button {font:20px sans-serif;margin:8px}
#overlay {position:fixed;inset:0;background:white;z-index:100;display:none}</style>
<h1>Synthetic normal input acceptance</h1>
<label>Verification text<input id="text" autocomplete="off"></label>
<button id="save">Save locally</button><output id="result">Not saved</output>
<div id="overlay">Covered</div><input id="other" aria-label="Other field">
<p id="events">0</p>
<script>
const text = document.querySelector('#text'), save = document.querySelector('#save');
let clicks = 0;
save.addEventListener('click', e => {
    if (!e.isTrusted) throw new Error('Synthetic click rejected');
    document.querySelector('#result').textContent = text.value;
    document.querySelector('#events').textContent = String(++clicks);
});
</script>"""


@pytest.fixture
async def page() -> AsyncIterator[Page]:
    async with async_patchright() as driver:
        endpoint = os.environ.get("NORMAL_INPUT_CDP_URL")
        browser = (
            await driver.chromium.connect_over_cdp(
                endpoint, headers={"Host": "localhost"}, no_defaults=True
            )
            if endpoint
            else await driver.chromium.launch(channel="msedge", headless=True)
        )
        try:
            if endpoint:
                assert len(browser.contexts) == 1 and len(browser.contexts[0].pages) == 1
                selected = browser.contexts[0].pages[0]
            else:
                selected = await browser.new_page()
            # Route fulfillment is test setup, scoped to this fictional synthetic URL.
            await selected.route(
                URL + "**", lambda route: route.fulfill(body=FORM, content_type="text/html")
            )
            await selected.goto(URL)
            yield selected
        finally:
            await browser.close()


@dataclass
class LeaseHarness:
    store: PostgresLeaseStore
    command: BrowserCommand
    engine: AsyncEngine

    def guard(self) -> AbstractAsyncContextManager[None]:
        return self.store.executor_action_guard(self.command)


@pytest.fixture
async def lease(database_url: str) -> AsyncIterator[LeaseHarness]:
    engine = create_async_engine(database_url)
    store = PostgresLeaseStore(engine)
    command = BrowserCommand.model_validate(
        command_payload() | {"action": "acquire", "sub": "input-" + uuid4().hex}
    )
    await store.register(command.session_id, command.sub, command.task_id, command.authorization_id)
    acquired = await store.execute(command)
    check = command.model_copy(update={"action": "check", "lease_id": acquired.lease_id})
    try:
        yield LeaseHarness(store, check, engine)
    finally:
        # Test-only registry is not the physical Steel lifecycle. Browser fixture
        # disconnects independently; the isolated DB container removes its own rows.
        await engine.dispose()


def adapter(page: Page, lease: LeaseHarness) -> NormalUIInput:
    return NormalUIInput(page, expected_url=URL, action_guard=lease.guard)


@pytest.mark.asyncio
async def test_normal_keyboard_click_and_readback(page: Page, lease: LeaseHarness) -> None:
    ui = adapter(page, lease)
    await ui.type_text(await ui.observe("textbox", "Verification text"), "CareerAct 合成核验")
    button = await ui.observe("button", "Save locally")
    await ui.click(button)
    assert await page.locator("#result").inner_text() == "CareerAct 合成核验"
    assert await page.locator("#events").inner_text() == "1"
    with pytest.raises(UIInputRejected):
        await ui.click(button)
    assert await page.locator("#events").inner_text() == "1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "save.hidden = true",
        "save.disabled = true",
        "document.querySelector('#overlay').style.display = 'block'",
        "save.style.opacity = '0'",
        "save.style.position = 'absolute'; save.style.top = '3000px'",
        "save.after(save.cloneNode(true))",
        "save.replaceWith(save.cloneNode(true))",
        "save.textContent = 'Different task'",
    ],
)
async def test_changed_target_cannot_receive_click(
    page: Page, lease: LeaseHarness, mutation: str
) -> None:
    ui = adapter(page, lease)
    target = await ui.observe("button", "Save locally")
    # Local fixture mutations simulate UI races, not operations against a real site.
    await page.evaluate("() => { const save = document.querySelector('#save'); " + mutation + " }")
    with pytest.raises(UIInputRejected):
        await ui.click(target)
    assert await page.locator("#events").inner_text() == "0"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boundary", ["readonly", "control_character", "wrong_adapter", "expired", "navigation"]
)
async def test_task_and_text_boundaries_reject_before_input(
    page: Page, lease: LeaseHarness, boundary: str
) -> None:
    ui = adapter(page, lease)
    target = await ui.observe("textbox", "Verification text")
    if boundary == "readonly":
        await page.evaluate("document.querySelector('#text').readOnly = true")
    elif boundary == "wrong_adapter":
        ui = adapter(page, lease)
    elif boundary == "expired":
        target.observed_at -= 10
    elif boundary == "navigation":
        await page.goto(URL + "?different-task")
    with pytest.raises(UIInputRejected):
        await ui.type_text(
            target, "unsafe\ninput" if boundary == "control_character" else "Synthetic"
        )
    assert await page.locator("#text").input_value() == ""


@pytest.mark.asyncio
async def test_focus_hijack_stops_remaining_text(page: Page, lease: LeaseHarness) -> None:
    ui = adapter(page, lease)
    await page.evaluate("""() => document.querySelector('#text').addEventListener(
        'input', () => document.querySelector('#other').focus(), {once: true})""")
    with pytest.raises(UIInputUncertain):
        await ui.type_text(await ui.observe("textbox", "Verification text"), "Synthetic")
    assert await page.locator("#text").input_value() == "S"
    assert await page.locator("#other").input_value() == ""
    with pytest.raises(UIInputRejected):
        await ui.observe("button", "Save locally")


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["revoke", "takeover", "expired_command"])
async def test_control_change_rejects_observed_target(
    page: Page, lease: LeaseHarness, transition: str
) -> None:
    ui = adapter(page, lease)
    target = await ui.observe("button", "Save locally")
    if transition == "revoke":
        await lease.store.revoke(lease.command.session_id)
    elif transition == "takeover":
        await lease.store.execute(
            lease.command.model_copy(update={"action": "stop", "jti": uuid4()})
        )
    else:
        lease.command = lease.command.model_copy(update={"iat": 1, "exp": 61})
    with pytest.raises((CommandRejected, LeaseConflict)):
        await ui.click(target)
    assert await page.locator("#events").inner_text() == "0"


@pytest.mark.asyncio
async def test_cancel_after_dispatch_does_not_allow_replay(page: Page, lease: LeaseHarness) -> None:
    dispatched = asyncio.Event()
    finish = asyncio.Event()
    hold_exit = False

    @asynccontextmanager
    async def guarded() -> AsyncIterator[None]:
        async with lease.guard():
            yield
            if hold_exit:
                dispatched.set()
                await finish.wait()

    ui = NormalUIInput(page, expected_url=URL, action_guard=guarded)
    target = await ui.observe("button", "Save locally")
    hold_exit = True
    task = asyncio.create_task(ui.click(target))
    async with asyncio.timeout(4):
        await dispatched.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await page.locator("#events").inner_text() == "1"
    with pytest.raises(UIInputRejected):
        await ui.observe("button", "Save locally")
    assert await page.locator("#events").inner_text() == "1"


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["takeover", "revoke"])
async def test_control_change_waits_for_inflight_input(
    page: Page, lease: LeaseHarness, transition: str
) -> None:
    entered = asyncio.Event()
    finish = asyncio.Event()
    hold_exit = False

    @asynccontextmanager
    async def guarded() -> AsyncIterator[None]:
        async with lease.guard():
            yield
            if hold_exit:
                entered.set()
                await finish.wait()

    ui = NormalUIInput(page, expected_url=URL, action_guard=guarded)
    button = await ui.observe("button", "Save locally")
    hold_exit = True
    operation = asyncio.create_task(ui.click(button))
    async with asyncio.timeout(4):
        await entered.wait()
        changing = asyncio.create_task(
            lease.store.revoke(lease.command.session_id)
            if transition == "revoke"
            else lease.store.execute(
                lease.command.model_copy(update={"action": "stop", "jti": uuid4()})
            )
        )
        try:
            await asyncio.sleep(0.1)
            assert not changing.done()
        finally:
            finish.set()
            await operation
            await changing
    with pytest.raises((CommandRejected, LeaseConflict)):
        await ui.observe("button", "Save locally")
    assert await page.locator("#events").inner_text() == "1"


@pytest.mark.asyncio
async def test_command_expiry_after_input_keeps_uncertain_result(
    page: Page, lease: LeaseHarness
) -> None:
    hold_exit = False

    @asynccontextmanager
    async def guarded() -> AsyncIterator[None]:
        async with lease.guard():
            yield
            if hold_exit:
                await asyncio.sleep(2.1)

    ui = NormalUIInput(page, expected_url=URL, action_guard=guarded)
    button = await ui.observe("button", "Save locally")
    async with lease.engine.connect() as database:
        now = int(await database.scalar(sql_text("SELECT EXTRACT(EPOCH FROM clock_timestamp())")))
    lease.command = lease.command.model_copy(update={"iat": now, "exp": now + 2})
    hold_exit = True
    with pytest.raises(UIInputUncertain):
        await ui.click(button)
    assert await page.locator("#events").inner_text() == "1"
    with pytest.raises((UIInputRejected, CommandRejected)):
        await ui.observe("button", "Save locally")


@pytest.mark.asyncio
async def test_steel_viewer_and_executor_share_unchanged_page(
    page: Page, lease: LeaseHarness
) -> None:
    api_url = os.environ.get("NORMAL_INPUT_STEEL_URL")
    if not api_url:
        pytest.skip("Requires isolated Steel canary, not a product session")
    remote = await page.context.new_cdp_session(page)
    try:
        info = await remote.send("Target.getTargetInfo")
        page_id = str(info["targetInfo"]["targetId"])
    finally:
        await remote.detach()
    dimensions = "({width:innerWidth,height:innerHeight})"
    before = await page.evaluate(dimensions)
    query = urlencode({"pageId": page_id, "readOnly": "true"})
    stream_url = api_url.replace("http://", "ws://", 1) + "/v1/sessions/cast?" + query
    ui = adapter(page, lease)
    async with connect(stream_url, max_size=2 * 1024 * 1024) as stream:
        await receive_frame(stream, page_id, "CareerAct normal input canary")
        assert await page.evaluate(dimensions) == before
        await ui.type_text(await ui.observe("textbox", "Verification text"), "Shared Viewer")
        await ui.click(await ui.observe("button", "Save locally"))
        assert await page.locator("#result").inner_text() == "Shared Viewer"
        await receive_frame(stream, page_id, "CareerAct normal input canary")
    # Reconnect the same synthetic page after viewer disconnect. No task recreation.
    async with connect(stream_url, max_size=2 * 1024 * 1024) as replacement:
        await receive_frame(replacement, page_id, "CareerAct normal input canary")
        assert await page.evaluate(dimensions) == before
        assert await page.locator("#events").inner_text() == "1"
    async with httpx.AsyncClient(base_url=api_url, timeout=10) as client:
        inventory = await client.get("/v1/sessions")
        inventory.raise_for_status()
        sessions = [entry for entry in inventory.json()["sessions"] if entry["status"] == "live"]
        assert len(sessions) == 1
        details = await client.get(f"/v1/sessions/{sessions[0]['id']}/live-details")
        details.raise_for_status()
        assert page_id in {entry["id"] for entry in details.json()["pages"]}


@pytest.mark.asyncio
async def test_native_human_input_relay_uses_lease_and_real_steel(
    page: Page, lease: LeaseHarness
) -> None:
    api_url = os.environ.get("NORMAL_INPUT_STEEL_URL")
    if not api_url:
        pytest.skip("Requires isolated Steel canary")
    remote = await page.context.new_cdp_session(page)
    try:
        info = await remote.send("Target.getTargetInfo")
        page_id = str(info["targetInfo"]["targetId"])
    finally:
        await remote.detach()
    old_lease = lease.command.lease_id
    assert old_lease is not None
    await lease.store.execute(lease.command.model_copy(update={"action": "stop", "jti": uuid4()}))
    await lease.store.confirm_stopped(lease.command.session_id, old_lease)
    viewer = lease.command.model_copy(
        update={"action": "viewer", "lease_id": None, "owner_id": "viewer", "jti": uuid4()}
    )
    human_lease = await lease.store.acquire_viewer(viewer)
    messages: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    frame_ready = asyncio.Event()
    sent: list[str] = []

    class SyntheticWebClient:
        async def receive(self) -> dict[str, object]:
            return await messages.get()

        async def send_text(self, value: str) -> None:
            payload = json.loads(value)
            if payload.get("pageId") == page_id and payload.get("data"):
                frame_ready.set()

        async def send_bytes(self, value: bytes) -> None:
            pytest.fail("Pinned Steel sends text frames")

    class ObservedUpstream:
        def __init__(self, stream: Any) -> None:
            self.stream = stream

        async def send(self, value: str) -> None:
            sent.append(value)
            await self.stream.send(value)

        def __aiter__(self) -> Any:
            return self.stream.__aiter__()

    async def send(kind: str, event: dict[str, object], *, target: str = page_id) -> None:
        await messages.put(
            {
                "type": "websocket.receive",
                "text": json.dumps({"type": kind, "pageId": target, "event": event}),
            }
        )

    async def click(selector: str) -> None:
        bounds = await page.locator(selector).bounding_box()
        assert bounds is not None
        for event_type in ("mousePressed", "mouseReleased"):
            await send(
                "mouseEvent",
                {
                    "type": event_type,
                    "x": bounds["x"] + bounds["width"] / 2,
                    "y": bounds["y"] + bounds["height"] / 2,
                    "button": "left",
                    "clickCount": 1,
                    "modifiers": 0,
                },
            )

    async def until(selector: str, expected: str, *, input_value: bool = False) -> None:
        async with asyncio.timeout(5):
            while (
                await page.locator(selector).input_value()
                if input_value
                else await page.locator(selector).inner_text()
            ) != expected:
                await asyncio.sleep(0.05)

    query = urlencode({"pageId": page_id})
    stream_url = api_url.replace("http://", "ws://", 1) + "/v1/sessions/cast?" + query
    try:
        async with connect(stream_url, max_size=2 * 1024 * 1024) as stream:
            relay = asyncio.create_task(
                _relay_websocket(
                    cast(WebSocket, SyntheticWebClient()),
                    ObservedUpstream(stream),
                    authorization_check=lambda: lease.store.check_viewer(
                        viewer, human_lease.lease_id
                    ),
                    authorization_renew=lambda: lease.store.renew_viewer(
                        viewer, human_lease.lease_id
                    ),
                    input_guard=lambda: lease.store.viewer_input_guard(
                        viewer, human_lease.lease_id
                    ),
                    page_id=page_id,
                )
            )
            try:
                await asyncio.wait_for(frame_ready.wait(), timeout=10)
                await click("#text")
                for key in "中A":
                    for event_type in ("keyDown", "keyUp"):
                        await send(
                            "keyEvent",
                            {
                                "type": event_type,
                                "key": key,
                                "text": key,
                                "code": "",
                                "keyCode": ord(key),
                            },
                        )
                await until("#text", "中A", input_value=True)
                await click("#save")
                await until("#result", "中A")
                assert await page.locator("#events").inner_text() == "1"
                count = len(sent)
                await send(
                    "keyEvent",
                    {"type": "keyDown", "key": "x", "text": "x", "code": "KeyX", "keyCode": 88},
                    target="forged-page",
                )
                with pytest.raises(ViewerRejected):
                    await asyncio.wait_for(relay, timeout=5)
                assert len(sent) == count
            finally:
                relay.cancel()
                await asyncio.gather(relay, return_exceptions=True)
    finally:
        await lease.store.drain_viewer(viewer, human_lease.lease_id)
        await lease.store.confirm_stopped(viewer.session_id, human_lease.lease_id)
