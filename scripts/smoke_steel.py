import argparse
import asyncio
from urllib.parse import urlsplit, urlunsplit

import httpx
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Playwright, async_playwright


async def check_viewer(
    playwright: Playwright, remote_page: Page, api_url: str, channel: str
) -> None:
    session = await remote_page.context.new_cdp_session(remote_page)
    info = await session.send("Target.getTargetInfo")
    await session.detach()
    viewer_browser = await playwright.chromium.launch(channel=channel)
    try:
        viewer = await viewer_browser.new_page(viewport={"width": 1920, "height": 900})
        await viewer.goto(
            api_url.rstrip("/") + "/v1/sessions/debug?pageId=" + info["targetInfo"]["targetId"]
        )
        await viewer.wait_for_function(
            """() => {
                const canvas = document.querySelector('canvas');
                return canvas && canvas.width > 0 &&
                    canvas.getContext('2d').getImageData(0, 0, 1, 1).data[3] > 0;
            }""",
            timeout=20000,
        )
        canvas = viewer.locator("canvas:visible").first
        print("PASS: Viewer received a rendered frame", flush=True)
        viewport = await remote_page.evaluate("({width: innerWidth, height: innerHeight})")
        for selector in ("input", "button"):
            target = await remote_page.locator(selector).bounding_box()
            bounds = await canvas.bounding_box()
            if target is None or bounds is None:
                raise RuntimeError("Viewer or remote target has no bounds")
            await canvas.click(
                position={
                    "x": (target["x"] + target["width"] / 2) * bounds["width"] / viewport["width"],
                    "y": (target["y"] + target["height"] / 2)
                    * bounds["height"]
                    / viewport["height"],
                }
            )
            if selector == "input":
                await viewer.keyboard.press("End")
                await viewer.keyboard.type("Viewer takeover", delay=30)
                await remote_page.wait_for_function(
                    "document.querySelector('input').value === 'CareerAct smokeViewer takeover'",
                    timeout=5000,
                )
        await remote_page.wait_for_function(
            "document.querySelector('output').textContent === 'CareerAct smokeViewer takeover'"
        )
        print("PASS: Viewer receives frames and forwards mouse/keyboard input")
    finally:
        await viewer_browser.close()


async def check(api_url: str, cdp_url: str, viewer_channel: str | None = None) -> None:
    async with httpx.AsyncClient(base_url=api_url, timeout=40) as client:
        health = await client.get("/v1/health")
        health.raise_for_status()
        sessions = await client.get("/v1/sessions")
        sessions.raise_for_status()
        if any(session["status"] == "live" for session in sessions.json()["sessions"]):
            raise RuntimeError("A live session exists; refusing to disturb it")
        created = await client.post("/v1/sessions", json={})
        created.raise_for_status()
        session_id = created.json()["id"]
        try:
            version = await client.get(
                cdp_url.rstrip("/") + "/json/version", headers={"Host": "localhost"}
            )
            version.raise_for_status()
            discovered = urlsplit(version.json()["webSocketDebuggerUrl"])
            target = urlsplit(cdp_url)
            websocket_url = urlunsplit(("ws", target.netloc, discovered.path, discovered.query, ""))
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(
                    websocket_url, headers={"Host": "localhost"}
                )
                try:
                    page = await browser.contexts[0].new_page()
                    await page.set_content(
                        '<label>Name<input></label><button onclick="'
                        "document.querySelector('output').textContent="
                        "document.querySelector('input').value"
                        '">Save</button><output></output>'
                    )
                    await page.get_by_role("textbox").fill("CareerAct smoke")
                    await page.get_by_role("button", name="Save").click()
                    if await page.locator("output").inner_text() != "CareerAct smoke":
                        raise RuntimeError("Page verification failed")
                    page_session = await page.context.new_cdp_session(page)
                    page_info = await page_session.send("Target.getTargetInfo")
                    await page_session.detach()
                    page_id = page_info["targetInfo"]["targetId"]
                    for _attempt in range(3):
                        details = await client.get(f"/v1/sessions/{session_id}/live-details")
                        details.raise_for_status()
                        payload = details.json()
                        if page_id not in {item["id"] for item in payload["pages"]}:
                            raise RuntimeError("Repeated page discovery lost the owned page")
                        version_info = payload["browserState"]["browserVersion"]
                        if not isinstance(version_info, str) or not version_info.startswith(
                            ("Chrome/", "HeadlessChrome/")
                        ):
                            raise RuntimeError(
                                "Page discovery must return browser version metadata"
                            )
                    print("PASS: Repeated page discovery retains ownership and version metadata")
                    viewer = await client.get("/v1/sessions/debug")
                    viewer.raise_for_status()
                    if "text/html" not in viewer.headers.get("content-type", ""):
                        raise RuntimeError("Viewer did not return HTML")
                    if viewer_channel:
                        await check_viewer(playwright, page, api_url, viewer_channel)
                    await page.close()
                finally:
                    await browser.close()
        finally:
            released = await client.post(f"/v1/sessions/{session_id}/release")
            released.raise_for_status()
            if not released.json().get("success"):
                raise RuntimeError("Session release failed")
        print("PASS: Steel health, session, CDP fill/click/read, viewer HTML and release")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:3001")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9223")
    parser.add_argument("--viewer-channel", help="Installed browser channel, e.g. msedge")
    args = parser.parse_args()
    try:
        asyncio.run(check(args.api_url, args.cdp_url, args.viewer_channel))
    except (httpx.HTTPError, PlaywrightError, RuntimeError) as error:
        parser.exit(1, f"Steel smoke failed: {type(error).__name__}; no session URLs logged.\n")


if __name__ == "__main__":
    main()
