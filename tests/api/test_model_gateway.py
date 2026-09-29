import os
import secrets
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from scripts.manage_model_key import (
    POLICY,
    KeyManagementError,
    checked_request,
    key_hash,
    provision,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MODEL_GATEWAY_TESTS") != "1",
    reason="Opt-in isolated LiteLLM OSS and PostgreSQL integration",
)
ROOT = Path(__file__).resolve().parents[2]


def docker(*arguments: str) -> str:
    result = subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, timeout=120, check=False
    )
    if result.returncode:
        pytest.fail(f"Isolated Docker {arguments[0]} failed; output withheld")
    return result.stdout.strip()


@pytest.fixture(scope="module")
def gateway(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, str]]:
    directory = tmp_path_factory.mktemp("model-gateway")
    name = "careeract-model-test-" + uuid4().hex[:10]
    database = name + "-db"
    images = [
        line.strip().removeprefix("image: ")
        for line in (ROOT / "compose.yaml").read_text().splitlines()
        if "image:" in line
    ]
    postgres_image = next(image for image in images if image.startswith("postgres:"))
    gateway_image = next(image for image in images if image.startswith("docker.litellm.ai/"))
    master = "sk-" + secrets.token_hex(32)
    configuration = directory / "config.yaml"
    configuration.write_text(
        "model_list:\n"
        + "".join(
            f"  - model_name: {model}\n"
            "    litellm_params:\n"
            "      model: openai/gpt-4o-mini\n"
            "      api_key: unused-synthetic-provider\n"
            "      mock_response: isolated gateway response\n"
            for model in ["careeract-default", "careeract-openai", "forbidden-model"]
        )
        + "general_settings:\n"
        "  master_key: os.environ/LITELLM_MASTER_KEY\n"
        "  database_url: os.environ/DATABASE_URL\n"
        "litellm_settings:\n"
        "  set_verbose: false\n",
        encoding="utf-8",
    )
    environment = directory / ".env"
    environment.write_text(
        f"DATABASE_URL=postgresql://postgres@{database}:5432/litellm\n"
        f"LITELLM_MASTER_KEY={master}\n"
        f"LITELLM_SALT_KEY={secrets.token_hex(32)}\n",
        encoding="utf-8",
    )
    try:
        docker("network", "create", name)
        docker(
            "run",
            "-d",
            "--name",
            database,
            "--network",
            name,
            "--tmpfs",
            "/var/lib/postgresql/data",
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "-e",
            "POSTGRES_DB=litellm",
            postgres_image,
        )
        for attempt in range(30):
            ready = subprocess.run(
                ["docker", "exec", database, "pg_isready", "-U", "postgres"],
                capture_output=True,
                timeout=5,
            )
            if ready.returncode == 0:
                break
            if attempt == 29:
                pytest.fail("Isolated PostgreSQL readiness timed out")
            time.sleep(1)
        docker(
            "run",
            "-d",
            "--name",
            name,
            "--network",
            name,
            "--env-file",
            str(environment),
            "-p",
            "127.0.0.1::4000",
            "--mount",
            f"type=bind,source={configuration},target=/app/config.yaml,readonly",
            gateway_image,
            "--config",
            "/app/config.yaml",
            "--port",
            "4000",
        )
        port = docker("port", name, "4000/tcp").rsplit(":", 1)[1]
        address = f"http://127.0.0.1:{port}"
        with httpx.Client(base_url=address, timeout=2, trust_env=False) as client:
            for attempt in range(120):
                try:
                    if client.get("/health/readiness").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                if attempt == 119:
                    pytest.fail("Isolated LiteLLM readiness timed out")
                time.sleep(1)
        yield address, master
    finally:
        for container in (name, database):
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=30)
        subprocess.run(["docker", "network", "rm", name], capture_output=True, timeout=30)
        environment.unlink(missing_ok=True)


def test_restricted_key_with_real_oss_gateway(gateway: tuple[str, str]) -> None:
    address, master = gateway
    key = "sk-" + secrets.token_hex(32)
    body = {"model": "careeract-default", "messages": [{"role": "user", "content": "probe"}]}
    with (
        httpx.Client(
            base_url=address,
            headers={"Authorization": f"Bearer {master}"},
            timeout=30,
            trust_env=False,
        ) as admin,
        httpx.Client(
            base_url=address,
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
            trust_env=False,
        ) as service,
    ):
        provision(admin, key)
        provision(admin, key)
        for model in POLICY["models"]:
            time.sleep(1)
            response = service.post("/chat/completions", json={**body, "model": model})
            assert response.status_code == 200, (
                f"Allowed model {model} status={response.status_code}; "
                f"parallel={'parallel' in response.text.lower()}; "
                f"tpm={'tpm' in response.text.lower()}; rpm={'rpm' in response.text.lower()}"
            )
            assert (
                response.json()["choices"][0]["message"]["content"] == "isolated gateway response"
            )
        time.sleep(1)
        with service.stream(
            "POST", "/v1/chat/completions", json={**body, "stream": True}
        ) as stream:
            assert stream.status_code == 200
            assert "data: [DONE]" in "".join(stream.iter_text())
        time.sleep(1)
        denied = service.post("/chat/completions", json={**body, "model": "forbidden-model"})
        assert denied.status_code in {401, 403}, f"Model restriction status={denied.status_code}"
        for method, path, payload in [
            ("POST", "/key/generate", {"models": ["careeract-default"]}),
            ("POST", "/key/update", {"key": key_hash(key), "models": ["forbidden-model"]}),
            ("POST", "/key/delete", {"keys": [key_hash(key)]}),
            ("GET", "/key/list", None),
            (
                "POST",
                "/model/new",
                {"model_name": "probe", "litellm_params": {"model": "gpt-4o-mini"}},
            ),
            ("POST", "/model/delete", {"id": "nonexistent-probe"}),
            ("GET", "/config/cost_discount_config", None),
        ]:
            response = service.request(method, path, json=payload)
            assert response.status_code in {401, 403}, (
                f"Management restriction {path}: {response.status_code}"
            )
        models = service.get("/v1/models")
        assert models.status_code == 200
        assert {item["id"] for item in models.json()["data"]} == set(POLICY["models"])
        replacement = "sk-" + secrets.token_hex(32)
        provision(admin, replacement)
        checked_request(admin, "POST", "/key/block", json={"key": key_hash(key)})
        with pytest.raises(KeyManagementError, match="blocked"):
            provision(admin, key)
        revoked = service.post("/chat/completions", json=body)
        assert revoked.status_code in {401, 403}, f"Revocation status={revoked.status_code}"
        response = service.post(
            "/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {replacement}"},
        )
        assert response.status_code == 200, f"Replacement key status={response.status_code}"
        checked_request(admin, "POST", "/key/delete", json={"keys": [key_hash(replacement)]})


def test_budget_and_rate_limits_with_real_oss_gateway(gateway: tuple[str, str]) -> None:
    address, master = gateway
    body = {"model": "careeract-default", "messages": [{"role": "user", "content": "probe"}]}
    with httpx.Client(
        base_url=address, headers={"Authorization": f"Bearer {master}"}, timeout=30, trust_env=False
    ) as admin:
        cases: list[tuple[str, dict[str, Any]]] = [
            ("budget", {"max_budget": 0.01, "spend": 1.0}),
            ("rpm", {"rpm_limit": 1}),
            ("tpm", {"tpm_limit": 1}),
        ]
        for limit, overrides in cases:
            key = "sk-" + secrets.token_hex(32)
            checked_request(
                admin, "POST", "/key/generate", json={"key": key, **POLICY, **overrides}
            )
            with httpx.Client(
                base_url=address,
                headers={"Authorization": f"Bearer {key}"},
                timeout=30,
                trust_env=False,
            ) as service:
                if limit == "rpm":
                    assert service.post("/chat/completions", json=body).status_code == 200
                response = service.post("/chat/completions", json=body)
                assert response.status_code == 429, (
                    f"{limit} restriction status={response.status_code}"
                )
            checked_request(admin, "POST", "/key/delete", json={"keys": [key_hash(key)]})
