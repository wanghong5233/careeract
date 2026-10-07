"""Verify Steel starts clean isolated browser contexts without touching a real site."""

import argparse
import asyncio
from typing import cast
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Playwright, async_playwright


def websocket_url(cdp_url: str, discovered_url: str) -> str:
    discovered = urlsplit(discovered_url)
    target = urlsplit(cdp_url)
    return urlunsplit(("ws", target.netloc, discovered.path, discovered.query, ""))


async def read_marker(playwright: Playwright, cdp_url: str, marker: str | None) -> str | None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(cdp_url.rstrip("/") + "/json/version")
        response.raise_for_status()
        version = response.json()
    browser = await playwright.chromium.connect_over_cdp(
        websocket_url(cdp_url, version["webSocketDebuggerUrl"]), headers={"Host": "localhost"}
    )
    try:
        page = await browser.contexts[0].new_page()
        await page.goto("https://example.com", wait_until="domcontentloaded", timeout=30_000)
        if marker is not None:
            await page.evaluate(
                "value => localStorage.setItem('careeract-profile-canary', value)", marker
            )
        return cast(
            str | None, await page.evaluate("localStorage.getItem('careeract-profile-canary')")
        )
    finally:
        await browser.close()


async def check(api_url: str, cdp_url: str) -> None:
    first_id = uuid4()
    second_id = uuid4()
    async with httpx.AsyncClient(base_url=api_url, timeout=40) as client:
        inventory = await client.get("/v1/sessions")
        inventory.raise_for_status()
        if any(item["status"] == "live" for item in inventory.json()["sessions"]):
            raise RuntimeError("A live Steel session exists; refusing to disturb it")

        async with async_playwright() as playwright:
            created: list[str] = []
            try:
                for session_id, profile_name, expected in (
                    (first_id, "careeract-profile-a", "profile-a"),
                    (second_id, "careeract-profile-b", None),
                ):
                    response = await client.post(
                        "/v1/sessions",
                        json={
                            "sessionId": str(session_id),
                            "userDataDir": f"/tmp/{profile_name}",
                            "persist": True,
                            "headless": True,
                            "credentials": {},
                        },
                    )
                    response.raise_for_status()
                    created.append(response.json()["id"])
                    observed = await read_marker(playwright, cdp_url, expected)
                    if observed != expected:
                        raise RuntimeError(
                            "Steel did not preserve the canary marker in its own session"
                        )
                    if session_id == first_id:
                        released = await client.post(f"/v1/sessions/{created[-1]}/release", json={})
                        released.raise_for_status()
                        created.pop()
                    else:
                        if observed is not None:
                            raise RuntimeError("Steel profile data leaked into a new session")
                print("PASS: separate Steel sessions start with isolated web storage")
            finally:
                for created_id in reversed(created):
                    await client.post(f"/v1/sessions/{created_id}/release", json={})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:3001")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9223")
    args = parser.parse_args()
    try:
        asyncio.run(check(args.api_url, args.cdp_url))
    except (httpx.HTTPError, PlaywrightError, RuntimeError) as error:
        parser.exit(
            1, f"Steel profile smoke failed: {type(error).__name__}; no credentials used.\n"
        )


if __name__ == "__main__":
    main()
