import argparse
import json
import secrets
import subprocess
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "data" / "stack-smoke.env"
BASE_URL = "http://localhost:18080"


def prepare() -> None:
    ENV_FILE.parent.mkdir(exist_ok=True)
    if ENV_FILE.exists():
        print("Smoke configuration already exists; preserved")
        return
    values = {
        "CAREERACT_DOMAIN": "http://localhost",
        "CAREERACT_URL": BASE_URL,
        "POSTGRES_USER": "careeract",
        "POSTGRES_PASSWORD": secrets.token_hex(24),
        "POSTGRES_DB": "careeract",
        "BETTER_AUTH_SECRET": secrets.token_hex(32),
        "LITELLM_MASTER_KEY": "sk-" + secrets.token_hex(24),
        "LITELLM_SALT_KEY": secrets.token_hex(32),
        "LITELLM_MODEL": "careeract-default",
        "OPENAI_API_KEY": "",
        "DASHSCOPE_API_KEY": "",
        "TEMPORAL_NAMESPACE": "default",
        "TEMPORAL_TASK_QUEUE": "careeract",
    }
    with ENV_FILE.open("x", encoding="utf-8") as output:
        output.write("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    print("Created ignored local-only smoke configuration; no provider keys used")


def compose(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            "careeract-smoke",
            "--env-file",
            str(ENV_FILE),
            "-f",
            "deploy/compose.yaml",
            "-f",
            "deploy/compose.smoke.yaml",
            *arguments,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )


def wait_web(client: httpx.Client) -> None:
    for attempt in range(60):
        try:
            ready = client.get("/api/auth/get-session")
            if ready.status_code == 200:
                return
        except httpx.TransportError:
            pass
        if attempt == 59:
            raise RuntimeError("Web did not become ready")
        time.sleep(1)


def check(restart: bool) -> None:
    with httpx.Client(base_url=BASE_URL, timeout=20, headers={"Origin": BASE_URL}) as client:
        wait_web(client)
        assert client.post("/api/agent", json={}).status_code == 401
        assert (
            client.post(
                "/api/agent", json={}, headers={"Origin": "http://untrusted.invalid"}
            ).status_code
            == 403
        )
        identity = uuid.uuid4().hex
        response = client.post(
            "/api/auth/sign-up/email",
            json={
                "name": "Container Probe",
                "email": f"{identity}@example.invalid",
                "password": secrets.token_urlsafe(24),
            },
        )
        assert response.status_code == 200, f"Registration status={response.status_code}"
        user_id = response.json()["user"]["id"]
        session = client.get("/api/auth/get-session")
        assert session.status_code == 200 and session.json()["user"]["id"] == user_id
        jwks = client.get("/api/auth/jwks")
        assert jwks.status_code == 200 and jwks.json()["keys"]
        upstream = client.post("/api/agent", json={})
        assert upstream.status_code == 422, f"Authenticated upstream status={upstream.status_code}"
        assert upstream.headers.get("x-request-id")
        if restart:
            compose("restart", "web", "api")
            compose("up", "-d", "--no-deps", "--no-build", "--wait", "api", "web")
            wait_web(client)
            restored = client.get("/api/auth/get-session")
            assert restored.json()["user"]["id"] == user_id
            assert client.get("/api/auth/jwks").json()["keys"] == jwks.json()["keys"]
            assert client.post("/api/agent", json={}).status_code == 422
            print("PASS: session and signing keys survive Web/API restart")
        assert client.post("/api/auth/sign-out", json={}).status_code == 200
        assert client.post("/api/agent", json={}).status_code == 401
        print("PASS: Caddy, signup, session, JWKS, BFF/JWT/API validation and signout")
        print("PASS: anonymous and wrong-origin requests rejected; no model call made")
    check_temporal()
    compose(
        "exec",
        "-T",
        "api",
        "/app/.venv/bin/python",
        "-c",
        "import httpx; "
        "urls=['http://browser:8001/health','http://steel:3000/v1/health',"
        "'http://litellm:4000/health/readiness']; "
        "[httpx.get(url,timeout=20).raise_for_status() for url in urls]",
    )
    print("PASS: Browser, Steel and LiteLLM reachable inside deployment network")


def check_temporal() -> None:
    for attempt in range(12):
        try:
            readiness = compose(
                "run",
                "--rm",
                "--no-deps",
                "--entrypoint",
                "temporal",
                "temporal-namespace",
                "task-queue",
                "describe",
                "--task-queue",
                "careeract",
                "--output",
                "json",
                "--address",
                "temporal:7233",
                "--client-connect-timeout",
                "2s",
                "--command-timeout",
                "3s",
            )
            if any(
                poller["taskQueueType"] == "workflow"
                for poller in (json.loads(readiness.stdout).get("pollers") or [])
            ):
                break
            print(f"Temporal readiness attempt {attempt + 1}/12: no workflow poller", flush=True)
        except subprocess.CalledProcessError:
            print(f"Temporal readiness attempt {attempt + 1}/12 failed", flush=True)
        if attempt == 11:
            raise RuntimeError("Temporal task queue did not become ready within probe budget")
        time.sleep(2)
    result = compose(
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "temporal",
        "temporal-namespace",
        "workflow",
        "execute",
        "--address",
        "temporal:7233",
        "--type",
        "SystemHealthWorkflow",
        "--task-queue",
        "careeract",
        "--workflow-id",
        "stack-smoke-" + uuid.uuid4().hex,
        "--execution-timeout",
        "30s",
    )
    if '"ok"' not in result.stdout:
        raise RuntimeError("Container Worker result not confirmed")
    print("PASS: PostgreSQL-backed Temporal and container Worker")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "check", "temporal"))
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "temporal":
        check_temporal()
    else:
        check(args.restart)


if __name__ == "__main__":
    main()
