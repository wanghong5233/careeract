import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.infrastructure.browser_control import BrowserCommandSigner
from services.browser.sessions.authentication import CommandVerifier
from services.browser.sessions.execution import ExecutorLifecycle, ExecutorUnavailable
from services.browser.sessions.postgres import PostgresLeaseStore
from tests.api.test_browser_control import control_context
from tests.browser.test_postgres_leases import database_url as database_url

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_VISIBLE_EXECUTOR_TEST") != "1"
    and os.environ.get("RUN_STEEL_EXECUTOR_TEST") != "1",
    reason="Opt-in Steel lifecycle test; visible mode additionally requires operator gates",
)


async def wait_gate(path: Path) -> None:
    async with asyncio.timeout(300):
        while not path.exists():
            await asyncio.sleep(0.2)


@pytest.mark.asyncio
async def test_stop_disconnect_and_page_survival(database_url: str) -> None:
    visible = os.environ.get("RUN_VISIBLE_EXECUTOR_TEST") == "1"
    gate_directory = Path(__file__).resolve().parents[2] / "data" / f"executor-{uuid4().hex}"
    if visible:
        gate_directory.mkdir(parents=True)
    engine = create_async_engine(database_url)
    store = PostgresLeaseStore(engine)
    async with httpx.AsyncClient(base_url="http://127.0.0.1:3001", timeout=30) as client:
        sessions = await client.get("/v1/sessions")
        sessions.raise_for_status()
        if any(session["status"] == "live" for session in sessions.json()["sessions"]):
            await engine.dispose()
            pytest.fail("A live Steel session exists; refusing to disturb it")
        created = await client.post("/v1/sessions", json={})
        created.raise_for_status()
        steel_session = created.json()["id"]
        try:
            version = await client.get(
                "http://127.0.0.1:9223/json/version", headers={"Host": "localhost"}
            )
            version.raise_for_status()
            discovered = urlsplit(version.json()["webSocketDebuggerUrl"])
            websocket = urlunsplit(("ws", "127.0.0.1:9223", discovered.path, discovered.query, ""))
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(
                    websocket, headers={"Host": "localhost"}
                )
                page = await browser.contexts[0].new_page()
                await page.set_content("""
                    <title>CareerAct executor verification</title>
                    <style>body{font:24px sans-serif;padding:32px;background:#eef2ff}
                    input,button{font:24px sans-serif;padding:12px;margin:12px 0}</style>
                    <h1>CareerAct executor verification</h1>
                    <p id="phase">Waiting for visible Viewer. Synthetic data only.</p>
                    <label>Verification text<br><input id="value"></label><br>
                    <button onclick="document.querySelector('output').textContent=
                    document.querySelector('input').value">Save locally</button><br>
                    <output>Not saved</output>
                """)
                cdp = await page.context.new_cdp_session(page)
                target = await cdp.send("Target.getTargetInfo")
                await cdp.detach()
                viewer_url = (
                    "http://127.0.0.1:3001/v1/sessions/debug?pageId="
                    + target["targetInfo"]["targetId"]
                )
                if visible:
                    (gate_directory / "viewer.txt").write_text(viewer_url, encoding="utf-8")
                    print(f"VISIBLE_GATE: {gate_directory}", flush=True)
                    await wait_gate(gate_directory / "start")
                context = control_context()
                key = Ed25519PrivateKey.generate()
                signer = BrowserCommandSigner(key)
                verifier = CommandVerifier(key.public_key())
                await store.manage(
                    verifier.verify(
                        signer.sign(context, "register"), context.session_id, "register"
                    )
                )
                lease = await store.execute(
                    verifier.verify(signer.sign(context, "acquire"), context.session_id, "acquire")
                )

                async def check() -> None:
                    await store.execute(
                        verifier.verify(
                            signer.sign(context, "check", lease.lease_id),
                            context.session_id,
                            "check",
                        )
                    )

                async def drain() -> None:
                    await store.execute(
                        verifier.verify(
                            signer.sign(context, "stop", lease.lease_id), context.session_id, "stop"
                        )
                    )

                async def disconnect() -> None:
                    await browser.close()
                    assert not browser.is_connected()

                async def release() -> None:
                    await store.confirm_stopped(context.session_id, lease.lease_id)

                executor = ExecutorLifecycle(
                    check_lease=check, mark_draining=drain, disconnect=disconnect, release=release
                )

                async def fill() -> None:
                    await page.locator("#phase").evaluate(
                        "element => element.textContent="
                        "'Agent writes, then disconnects. Next: human input.'"
                    )
                    await page.locator("input").fill("Agent verified")
                    await page.get_by_role("button").click()
                    assert await page.locator("output").inner_text() == "Agent verified"

                await executor.run(fill)
                await executor.stop()
                with pytest.raises(ExecutorUnavailable):
                    await executor.run(fill)
                with pytest.raises(PlaywrightError):
                    await page.locator("input").fill("Stale executor", timeout=1000)
                print(
                    "PASS: Agent drained, disconnected, released; stale object cannot write",
                    flush=True,
                )
                observer = await playwright.chromium.connect_over_cdp(
                    websocket, headers={"Host": "localhost"}
                )
                try:
                    matching_pages = [
                        candidate
                        for candidate in observer.contexts[0].pages
                        if await candidate.title() == "CareerAct executor verification"
                    ]
                    assert len(matching_pages) == 1
                    observed = matching_pages[0]
                    assert await observed.locator("output").inner_text() == "Agent verified"
                    if visible:
                        print(
                            "VISIBLE_INPUT: append ' Human verified' and click Save locally",
                            flush=True,
                        )
                        await observed.wait_for_function(
                            "document.querySelector('output').textContent === "
                            "'Agent verified Human verified'",
                            timeout=300000,
                        )
                        print(
                            "PASS: visible input verified; close the Viewer tab",
                            flush=True,
                        )
                        await wait_gate(gate_directory / "viewer-closed")
                    else:
                        print(
                            "PASS: page survives executor disconnection; Viewer input not tested",
                            flush=True,
                        )
                finally:
                    await observer.close()
                await store.revoke(context.session_id)
        finally:
            try:
                released = await client.post(f"/v1/sessions/{steel_session}/release")
                released.raise_for_status()
                assert released.json().get("success")
            finally:
                await engine.dispose()
