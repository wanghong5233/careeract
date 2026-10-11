import argparse
import asyncio
import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, async_playwright
from websockets.asyncio.client import ClientConnection, connect


def docker(*arguments: str) -> str:
    result = subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, check=False, timeout=60
    )
    if result.returncode:
        raise RuntimeError("Isolated Steel container command failed")
    return result.stdout.strip()


def published_port(container: str, port: int) -> int:
    published = json.loads(
        docker("inspect", "--format", "{{json .NetworkSettings.Ports}}", container)
    )
    bindings = published[f"{port}/tcp"]
    if len(bindings) != 1 or bindings[0]["HostIp"] != "127.0.0.1":
        raise RuntimeError("Canary must bind only to loopback")
    return int(bindings[0]["HostPort"])


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


async def receive_frame(
    connection: ClientConnection, page_id: str, title: str, timeout: float = 12
) -> dict[str, Any]:
    async with asyncio.timeout(timeout):
        while True:
            message = await connection.recv()
            payload = json.loads(message)
            if (
                payload.get("pageId") == page_id
                and payload.get("title") == title
                and isinstance(payload.get("data"), str)
                and len(payload["data"]) > 100
            ):
                return dict(payload)


async def drain_frames(connection: ClientConnection) -> None:
    for _attempt in range(100):
        try:
            await asyncio.wait_for(connection.recv(), timeout=0.05)
        except TimeoutError:
            return
    raise RuntimeError("Canary stream did not drain within its bound")


async def target_id(page: Page) -> str:
    client = await page.context.new_cdp_session(page)
    try:
        target = await client.send("Target.getTargetInfo")
        return str(target["targetInfo"]["targetId"])
    finally:
        await client.detach()


async def wait_ready(client: httpx.AsyncClient) -> None:
    async with asyncio.timeout(60):
        while True:
            try:
                response = await client.get("/v1/health", timeout=2)
                if response.status_code == 200:
                    return
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.5)


async def probe(
    api_url: str, cdp_url: str, report_directory: Path, visible: bool
) -> dict[str, Any]:
    report: dict[str, Any] = {"scope": "isolated synthetic Steel OSS viewer capabilities"}
    async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
        await wait_ready(client)
        created = await client.post("/v1/sessions", json={})
        created.raise_for_status()
        session_id = created.json()["id"]
        try:
            version = await client.get(cdp_url + "/json/version", headers={"Host": "localhost"})
            version.raise_for_status()
            discovered = urlsplit(version.json()["webSocketDebuggerUrl"])
            endpoint = urlsplit(cdp_url)
            cdp_websocket = urlunsplit(("ws", endpoint.netloc, discovered.path, "", ""))
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(
                    cdp_websocket, headers={"Host": "localhost"}
                )
                try:
                    page = await browser.contexts[0].new_page()
                    await page.set_viewport_size({"width": 1000, "height": 700})
                    await page.set_content(
                        "<title>CareerAct viewer canary</title>"
                        "<style>body{font:24px sans-serif;padding:36px;background:#eef2ff}"
                        "input,button{font:24px sans-serif;padding:12px}</style>"
                        "<h1>CareerAct browser capability check</h1>"
                        "<p>Synthetic data only. No BOSS account or messages.</p>"
                        "<input aria-label='Synthetic value'>"
                        "<button onclick=\"document.querySelector('output').textContent="
                        "document.querySelector('input').value\">Save locally</button>"
                        "<p><output>Waiting for executor</output></p><p id='clock'></p>"
                        "<script>setInterval(()=>document.getElementById('clock').textContent="
                        "String(Date.now()),200)</script>"
                    )
                    page_id = await target_id(page)
                    details = await client.get(f"/v1/sessions/{session_id}/live-details")
                    details.raise_for_status()
                    assert page_id in {entry["id"] for entry in details.json()["pages"]}
                    report["page_binding_verified"] = True
                    viewer_path = "/v1/sessions/debug?" + urlencode(
                        {"pageId": page_id, "interactive": "false"}
                    )
                    document = await client.get(viewer_path)
                    document.raise_for_status()
                    assert "const interactive = false" in document.text
                    report["native_readonly_ui_supported"] = True
                    before = await page.evaluate("({width:innerWidth,height:innerHeight})")
                    stream_url = api_url.replace("http://", "ws://", 1) + (
                        "/v1/sessions/cast?" + urlencode({"pageId": page_id, "readOnly": "true"})
                    )
                    async with connect(stream_url, max_size=2 * 1024 * 1024) as first:
                        await receive_frame(first, page_id, "CareerAct viewer canary")
                        after = await page.evaluate("({width:innerWidth,height:innerHeight})")
                        report["viewport_before"] = before
                        report["viewport_after"] = after
                        report["native_watch_preserves_viewport"] = before == after
                        await page.get_by_role("textbox").fill("Agent verified")
                        await page.get_by_role("button", name="Save locally").click()
                        assert await page.locator("output").inner_text() == "Agent verified"
                        await receive_frame(first, page_id, "CareerAct viewer canary")
                        report["executor_and_frames_coexist"] = True
                        async with connect(stream_url, max_size=2 * 1024 * 1024) as second:
                            await receive_frame(second, page_id, "CareerAct viewer canary")
                            await receive_frame(first, page_id, "CareerAct viewer canary")
                            report["two_native_streams_receive_frames"] = True
                            await page.get_by_role("textbox").focus()
                            await first.send(
                                json.dumps(
                                    {
                                        "type": "keyEvent",
                                        "event": {
                                            "type": "char",
                                            "text": "X",
                                            "key": "X",
                                            "code": "KeyX",
                                            "keyCode": 88,
                                        },
                                    }
                                )
                            )
                            try:
                                await page.wait_for_function(
                                    "document.querySelector('input').value === 'Agent verifiedX'",
                                    timeout=3000,
                                )
                                report["native_watch_rejects_forged_input"] = False
                            except PlaywrightError:
                                if (
                                    await page.get_by_role("textbox").input_value()
                                    != "Agent verified"
                                ):
                                    raise RuntimeError("Unexpected canary input state") from None
                                report["native_watch_rejects_forged_input"] = True
                            await drain_frames(second)
                            await first.close()
                            await first.wait_closed()
                            await asyncio.sleep(0.5)
                            await drain_frames(second)
                            await page.evaluate("document.title = 'CareerAct remaining viewer'")
                            try:
                                await receive_frame(
                                    second, page_id, "CareerAct remaining viewer", 5
                                )
                                report["closing_one_native_stream_preserves_other"] = True
                            except TimeoutError:
                                report["closing_one_native_stream_preserves_other"] = False
                    await browser.close()
                    report["executor_disconnected"] = not browser.is_connected()
                    try:
                        await page.get_by_role("textbox").fill("stale executor", timeout=1000)
                    except PlaywrightError:
                        report["old_page_handle_cannot_write"] = True
                    else:
                        raise RuntimeError("Disconnected executor retained writable page handle")
                    browser = await playwright.chromium.connect_over_cdp(
                        cdp_websocket, headers={"Host": "localhost"}
                    )
                    candidates = [
                        candidate
                        for candidate in browser.contexts[0].pages
                        if await target_id(candidate) == page_id
                    ]
                    assert len(candidates) == 1
                    page = candidates[0]
                    assert await page.locator("output").inner_text() == "Agent verified"
                    report["page_survives_executor_disconnect"] = True
                    report["raw_cdp_can_reconnect"] = True
                    async with connect(stream_url, max_size=2 * 1024 * 1024) as replacement:
                        await receive_frame(replacement, page_id, "CareerAct remaining viewer")
                        report["fresh_stream_receives_frames"] = True
                    await page.evaluate(
                        "document.title='CareerAct Phase 1.0';"
                        "document.querySelector('h1').textContent='CareerAct Phase 1.0';"
                        "document.querySelector('output').textContent="
                        "'Capability checks completed. Product watch/control integration pending.'"
                    )
                    report_directory.mkdir(parents=True, exist_ok=True)
                    (report_directory / "capabilities.json").write_text(
                        json.dumps(report, indent=2), encoding="utf-8"
                    )
                    print(json.dumps(report), flush=True)
                    if visible:
                        manifest = {"viewer_url": api_url + viewer_path}
                        (report_directory / "visible.json").write_text(
                            json.dumps(manifest), encoding="utf-8"
                        )
                        print("VISIBLE_READY: synthetic viewer; awaiting inspection", flush=True)
                        async with asyncio.timeout(180):
                            while not (report_directory / "inspection-complete").exists():
                                await asyncio.sleep(0.25)
                finally:
                    await browser.close()
        finally:
            released = await client.post(f"/v1/sessions/{session_id}/release")
            released.raise_for_status()
            assert released.json().get("success") is True
            inventory = await client.get("/v1/sessions")
            inventory.raise_for_status()
            assert not any(
                entry["id"] == session_id and entry["status"] == "live"
                for entry in inventory.json()["sessions"]
            )
            report["physical_release_verified"] = True
            report_directory.mkdir(parents=True, exist_ok=True)
            (report_directory / "capabilities.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="careeract-steel:0.5.3-compat")
    parser.add_argument("--report-directory", type=Path, required=True)
    parser.add_argument("--visible", action="store_true")
    arguments = parser.parse_args()
    if arguments.report_directory.exists():
        parser.error("Use a new report directory to avoid stale inspection gates")
    container = "careeract-viewer-canary-" + uuid4().hex[:12]
    image_id = docker("image", "inspect", "--format", "{{.Id}}", arguments.image)
    api_port = available_port()
    created = False
    started = time.monotonic()
    try:
        docker(
            "run",
            "--detach",
            "--pull=never",
            "--name",
            container,
            "--publish",
            f"127.0.0.1:{api_port}:3000",
            "--publish",
            "127.0.0.1::9223",
            "--shm-size",
            "512m",
            "--env",
            f"DOMAIN=127.0.0.1:{api_port}",
            image_id,
        )
        created = True
        api_url = f"http://127.0.0.1:{published_port(container, 3000)}"
        cdp_url = f"http://127.0.0.1:{published_port(container, 9223)}"
        report = asyncio.run(probe(api_url, cdp_url, arguments.report_directory, arguments.visible))
        report["image_id"] = image_id
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        (arguments.report_directory / "capabilities.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(
            "PASS: capability probe and physical release; native limitations recorded", flush=True
        )
    finally:
        if created:
            docker("rm", "--force", container)


if __name__ == "__main__":
    main()
