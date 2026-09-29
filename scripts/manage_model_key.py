import argparse
import hashlib
import os
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values
from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

MODELS = ["careeract-default", "careeract-openai"]
ROUTES = ["/chat/completions", "/v1/chat/completions", "/models", "/v1/models"]
POLICY: dict[str, Any] = {
    "models": MODELS,
    "allowed_routes": ROUTES,
    "max_budget": 5.0,
    "budget_duration": "30d",
    "rpm_limit": 30,
    "tpm_limit": 60000,
    "max_parallel_requests": 1,
}


class KeyManagementError(RuntimeError):
    pass


class ManagementSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    litellm_base_url: str = "http://localhost:4000"
    litellm_master_key: SecretStr


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def checked_request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    expected: tuple[int, ...] = (200,),
    **kwargs: Any,
) -> httpx.Response:
    try:
        response = client.request(method, path, **kwargs)
    except httpx.TransportError:
        raise KeyManagementError("Gateway transport failed; reconcile before retrying") from None
    if response.status_code not in expected:
        raise KeyManagementError(f"Gateway {method} {path} status={response.status_code}")
    return response


def check_policy(client: httpx.Client, key: str) -> None:
    response = checked_request(client, "GET", "/key/info", params={"key": key_hash(key)})
    try:
        info = response.json()["info"]
        if not isinstance(info, dict):
            raise KeyManagementError("Gateway returned malformed key metadata")
        matches = all(
            set(info.get(field) or []) == set(value)
            if isinstance(value, list)
            else info.get(field) == value
            for field, value in POLICY.items()
        )
    except (ValueError, KeyError, TypeError):
        raise KeyManagementError("Gateway returned malformed key metadata") from None
    if not matches or info.get("blocked"):
        raise KeyManagementError(
            "Existing service key policy differs or is blocked; rotate explicitly"
        )


def provision(client: httpx.Client, key: str) -> None:
    existing = checked_request(
        client, "GET", "/key/info", params={"key": key_hash(key)}, expected=(200, 404)
    )
    if existing.status_code == 200:
        check_policy(client, key)
        return
    response = checked_request(client, "POST", "/key/generate", json={"key": key, **POLICY})
    try:
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("key") != key:
            raise KeyManagementError(
                "Gateway did not confirm the requested key; reconcile manually"
            )
    except ValueError:
        raise KeyManagementError("Gateway returned malformed creation response") from None
    check_policy(client, key)


def load_key(path: Path, *, create: bool) -> str:
    if path.name != ".env.litellm" and not path.name.startswith(".env.litellm."):
        raise KeyManagementError("Use an ignored .env.litellm or .env.litellm.* file")
    if create and not path.exists():
        key = "sk-" + secrets.token_hex(32)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(f"LITELLM_API_KEY={key}\n")
    value = dotenv_values(path).get("LITELLM_API_KEY")
    if not value or not value.startswith("sk-"):
        raise KeyManagementError("Service key file is missing or invalid")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the restricted CareerAct inference key")
    parser.add_argument("action", choices=["prepare", "provision", "check", "revoke"])
    parser.add_argument("--key-file", type=Path, default=Path(".env.litellm"))
    parser.add_argument("--environment", action="store_true")
    args = parser.parse_args()
    try:
        key = (
            os.environ.get("LITELLM_API_KEY", "")
            if args.environment
            else load_key(args.key_file, create=args.action in {"prepare", "provision"})
        )
        if not key.strip():
            raise KeyManagementError("LITELLM_API_KEY is required")
        if args.action == "prepare":
            print("Service key file prepared; existing value preserved; not yet registered")
            return
        settings = ManagementSettings()  # type: ignore[call-arg]
        address = urlsplit(settings.litellm_base_url)
        if address.scheme not in {"http", "https"} or address.username or address.password:
            raise KeyManagementError("Use an HTTP(S) gateway URL without credentials")
        if secrets.compare_digest(key, settings.litellm_master_key.get_secret_value()):
            raise KeyManagementError("Service key must differ from the management key")
        with httpx.Client(
            base_url=settings.litellm_base_url,
            headers={"Authorization": "Bearer " + settings.litellm_master_key.get_secret_value()},
            timeout=30,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            if args.action == "provision":
                provision(client, key)
            elif args.action == "check":
                check_policy(client, key)
            else:
                checked_request(client, "POST", "/key/block", json={"key": key_hash(key)})
        print(f"Service key {args.action}: OK; no credential values displayed")
    except (KeyManagementError, ValidationError, OSError) as error:
        message = str(error) if isinstance(error, KeyManagementError) else type(error).__name__
        raise SystemExit(f"Key management failed: {message}") from None


if __name__ == "__main__":
    main()
