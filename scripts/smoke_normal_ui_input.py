"""Run the normal-input acceptance against a disposable fixed Steel image.

No daily Steel session, external account or private site is touched. PostgreSQL is
provided by the existing isolated pytest fixture. This is acceptance setup, not an
Agent executor or an alternative product session manager.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
from patchright.async_api import async_playwright as async_patchright

from scripts.smoke_steel_viewer import available_port, docker, published_port, wait_ready

ROOT = Path(__file__).resolve().parents[1]


async def acceptance(api_url: str, cdp_url: str, directory: Path) -> None:
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
            websocket = urlunsplit(("ws", endpoint.netloc, discovered.path, "", ""))
            async with async_patchright() as driver:
                browser = await driver.chromium.connect_over_cdp(
                    websocket, headers={"Host": "localhost"}, no_defaults=True
                )
                try:
                    assert len(browser.contexts) == 1
                    context = browser.contexts[0]
                    if not context.pages:
                        await context.new_page()
                    assert len(context.pages) == 1
                finally:
                    # Disconnect only. The isolated Steel session remains live.
                    await browser.close()
            env = os.environ | {
                "RUN_NORMAL_INPUT_TESTS": "1",
                "NORMAL_INPUT_CDP_URL": websocket,
                "NORMAL_INPUT_STEEL_URL": api_url,
            }
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/browser/test_ui_input.py",
                    "tests/browser/test_material_browser.py",
                    "-q",
                    "-x",
                    f"--junitxml={directory / 'tests.xml'}",
                ],
                cwd=ROOT,
                env=env,
                check=False,
                timeout=600,
            )
            if result.returncode:
                raise RuntimeError("Synthetic normal-input acceptance failed")
        finally:
            released = await client.post(f"/v1/sessions/{session_id}/release")
            released.raise_for_status()
            assert released.json().get("success") is True
            inventory = await client.get("/v1/sessions")
            inventory.raise_for_status()
            assert not any(
                item["id"] == session_id and item["status"] == "live"
                for item in inventory.json()["sessions"]
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="careeract-steel:0.5.3-compat")
    parser.add_argument("--report-directory", type=Path, required=True)
    args = parser.parse_args()
    directory = args.report_directory.resolve()
    if directory.exists():
        parser.error("Use a new report directory to avoid stale evidence")
    directory.mkdir(parents=True)
    container = "careeract-normal-input-canary-" + uuid4().hex[:12]
    image_id = docker("image", "inspect", "--format", "{{.Id}}", args.image)
    port = available_port()
    created = False
    try:
        docker(
            "run",
            "--detach",
            "--pull=never",
            "--name",
            container,
            "--publish",
            f"127.0.0.1:{port}:3000",
            "--publish",
            "127.0.0.1::9223",
            "--shm-size",
            "512m",
            "--env",
            f"DOMAIN=127.0.0.1:{port}",
            image_id,
        )
        created = True
        asyncio.run(
            acceptance(
                f"http://127.0.0.1:{published_port(container, 3000)}",
                f"http://127.0.0.1:{published_port(container, 9223)}",
                directory,
            )
        )
        (directory / "capabilities.json").write_text(
            json.dumps(
                {
                    "scope": "synthetic normal input; isolated Steel and PostgreSQL",
                    "driver": "patchright==1.63.0",
                    "image_id": image_id,
                    "pytest_passed": True,
                    "physical_release_verified": True,
                    "business_endpoints_opened": False,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("PASS: synthetic input, Viewer and physical release; business remains closed")
    finally:
        if created:
            docker("rm", "--force", container)


if __name__ == "__main__":
    main()
