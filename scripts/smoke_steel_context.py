import argparse
import asyncio
from uuid import UUID, uuid4

import httpx
from playwright.async_api import Browser, Playwright, async_playwright
from playwright.async_api import Error as PlaywrightError

from scripts.smoke_steel_profile import websocket_url

ORIGIN = "https://example.com"


async def inventory(client: httpx.AsyncClient) -> list[dict[str, object]]:
    response = await client.get("/v1/sessions")
    response.raise_for_status()
    sessions: list[dict[str, object]] = response.json()["sessions"]
    return sessions


async def require_owned(client: httpx.AsyncClient, session_id: UUID) -> None:
    active = [item for item in await inventory(client) if item["status"] == "live"]
    if len(active) != 1 or active[0]["id"] != str(session_id):
        raise RuntimeError("Steel ownership is uncertain; refusing further operations")


async def connect_browser(playwright: Playwright, cdp_url: str) -> Browser:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(cdp_url.rstrip("/") + "/json/version")
        response.raise_for_status()
    return await playwright.chromium.connect_over_cdp(
        websocket_url(cdp_url, response.json()["webSocketDebuggerUrl"]),
        headers={"Host": "localhost"},
    )


async def check(api_url: str, cdp_url: str) -> None:
    marker = uuid4().hex
    name = "careeract-context-" + marker
    saved: dict[str, object] | None = None
    async with httpx.AsyncClient(base_url=api_url, timeout=40) as client:
        if any(item["status"] == "live" for item in await inventory(client)):
            raise RuntimeError("Active Steel session exists; refusing to disturb it")
        async with async_playwright() as playwright:
            for stage in ("seed", "restore", "clean"):
                session_id = uuid4()
                body: dict[str, object] = {
                    "sessionId": str(session_id),
                    "headless": True,
                    "credentials": {},
                }
                if stage == "restore":
                    body["sessionContext"] = saved
                created = await client.post("/v1/sessions", json=body)
                created.raise_for_status()
                if created.json()["id"] != str(session_id):
                    raise RuntimeError("Steel creation unconfirmed; reconcile before retry")
                await require_owned(client, session_id)
                browser = await connect_browser(playwright, cdp_url)
                try:
                    context = browser.contexts[0]
                    page = await context.new_page()
                    await page.goto(ORIGIN, wait_until="domcontentloaded", timeout=30_000)
                    if stage == "seed":
                        await context.add_cookies(
                            [
                                {
                                    "name": name,
                                    "value": marker,
                                    "url": ORIGIN,
                                    "httpOnly": True,
                                    "secure": True,
                                    "sameSite": "Lax",
                                }
                            ]
                        )
                        await page.evaluate(
                            "item => localStorage.setItem(item.name, item.value)",
                            {"name": name, "value": marker},
                        )
                        await require_owned(client, session_id)
                        exported = await client.get(f"/v1/sessions/{session_id}/context")
                        exported.raise_for_status()
                        state = exported.json()
                        cookies = [
                            item for item in state.get("cookies", []) if item.get("name") == name
                        ]
                        stored = state.get("localStorage", {}).get("example.com", {}).get(name)
                        if len(cookies) != 1 or cookies[0]["value"] != marker or stored != marker:
                            raise RuntimeError("Native export did not preserve synthetic markers")
                        saved = {
                            "cookies": cookies,
                            "localStorage": {ORIGIN: {name: stored}},
                        }
                    else:
                        if stage == "restore":
                            await page.wait_for_function(
                                "item => localStorage.getItem(item.name) === item.value",
                                arg={"name": name, "value": marker},
                                timeout=5_000,
                            )
                        cookies = [
                            item for item in await context.cookies(ORIGIN) if item["name"] == name
                        ]
                        stored = await page.evaluate("name => localStorage.getItem(name)", name)
                        expected = marker if stage == "restore" else None
                        if (
                            cookies[0]["value"] if cookies else None
                        ) != expected or stored != expected:
                            raise RuntimeError("Native restore or clean-session isolation failed")
                        if cookies and not cookies[0]["httpOnly"]:
                            raise RuntimeError("Cookie security attributes changed")
                    print(f"PASS: synthetic native sessionContext {stage}")
                finally:
                    await browser.close()
                    await require_owned(client, session_id)
                    released = await client.post(f"/v1/sessions/{session_id}/release")
                    released.raise_for_status()
                    if (
                        released.json()["id"] != str(session_id)
                        or released.json()["status"] != "released"
                        or not any(
                            item["id"] == str(session_id) and item["status"] == "released"
                            for item in await inventory(client)
                        )
                    ):
                        raise RuntimeError("Steel release unconfirmed; reconcile before retry")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:3001")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9223")
    args = parser.parse_args()
    try:
        asyncio.run(check(args.api_url, args.cdp_url))
    except (httpx.HTTPError, PlaywrightError, RuntimeError) as error:
        parser.exit(
            1, f"Steel context canary failed: {type(error).__name__}; synthetic data only.\n"
        )


if __name__ == "__main__":
    main()
