import base64
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.app.factory import create_app
from tests.api.test_health import build_settings, use_signing_key
from tests.browser.test_postgres_leases import database_url as database_url


def token_for(private_key: Ed25519PrivateKey, user_id: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user_id,
            "iss": "http://localhost:3000",
            "aud": "http://localhost:3000",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="EdDSA",
        headers={"kid": "test-key"},
    )


class RuntimeOnly:
    def __init__(self) -> None:
        self.app = FastAPI()
        self.agents: list[object] = []

    def get_app(self) -> FastAPI:
        return self.app


def test_memories_require_identity_and_sanitize_invalid_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    app = create_app(build_settings(), lambda _settings: RuntimeOnly())
    headers = {"Authorization": "Bearer " + token_for(private_key, "synthetic-user")}
    marker = "SYNTHETIC_PRIVATE_TEXT"
    with TestClient(app) as client:
        assert client.get("/api/v1/memories").status_code == 401
        for body in (
            {"kind": "rule", "title": " ", "content": "内容"},
            {"kind": "unknown", "title": "标题", "content": "内容"},
            {"kind": "rule", "title": marker * 50, "content": "内容"},
            {"kind": "rule", "title": "标题", "content": "内容", "user_id": "another"},
            {"kind": "rule", "title": "标题", "content": "内容", "state": "confirmed"},
        ):
            response = client.post("/api/v1/memories", headers=headers, json=body)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "invalid_memory"
            assert marker not in response.text
            assert response.headers["cache-control"] == "no-store"
        for field in ("content", "source"):
            response = client.post(
                "/api/v1/memories",
                headers=headers,
                json={
                    "kind": "note",
                    "title": "标题",
                    "content": "内容",
                    field: "密码: synthetic-only",
                },
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "restricted_content"
            assert "synthetic-only" not in response.text


@pytest.mark.parametrize("payload", [None, [], {"updated_at": "2026-10-01", "id": str(uuid4())}])
def test_memories_reject_invalid_cursors(payload: object, monkeypatch: pytest.MonkeyPatch) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    app = create_app(build_settings(), lambda _settings: RuntimeOnly())
    headers = {"Authorization": "Bearer " + token_for(private_key, "synthetic-user")}
    cursor = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    with TestClient(app) as client:
        response = client.get("/api/v1/memories", headers=headers, params={"cursor": cursor})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_memory"


@pytest.mark.skipif(
    os.environ.get("RUN_PROJECT_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL memory integration",
)
@pytest.mark.asyncio
async def test_memories_are_scoped_and_conditionally_confirmed(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    settings = build_settings().model_copy(update={"database_url": PostgresDsn(database_url)})
    app = create_app(settings, lambda _settings: RuntimeOnly())
    engine = create_async_engine(database_url)
    first_user = "memory-first-" + uuid4().hex
    second_user = "memory-second-" + uuid4().hex
    project_id = uuid4()
    try:
        async with engine.begin() as connection:
            for user_id in (first_user, second_user):
                await connection.execute(
                    text(
                        'INSERT INTO auth."user" (id, name, email, "emailVerified") '
                        "VALUES (:user_id, 'Synthetic', :email, false)"
                    ),
                    {"user_id": user_id, "email": user_id + "@example.invalid"},
                )
            await connection.execute(
                text(
                    "INSERT INTO career.career_projects (id,user_id,title,purpose,status,version) "
                    "VALUES (:id,:user_id,'Synthetic project','','planned',:version)"
                ),
                {"id": project_id, "user_id": first_user, "version": uuid4()},
            )
        first_headers = {"Authorization": "Bearer " + token_for(private_key, first_user)}
        second_headers = {"Authorization": "Bearer " + token_for(private_key, second_user)}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                "/api/v1/memories",
                headers=first_headers,
                json={
                    "kind": "rule",
                    "title": "保留来源",
                    "content": "申请状态必须保留官方来源和核验时间。",
                },
            )
            assert created.status_code == 201
            memory = created.json()
            assert memory["state"] == "candidate"

            response = await client.post(
                "/api/v1/memories",
                headers=second_headers,
                json={
                    "project_id": str(project_id),
                    "kind": "note",
                    "title": "外部项目",
                    "content": "内容",
                },
            )
            assert response.status_code == 404

            hidden = await client.get("/api/v1/memories", headers=second_headers)
            assert hidden.status_code == 200
            assert hidden.json()["items"] == []
            forbidden = await client.get("/api/v1/memories/" + memory["id"], headers=second_headers)
            assert forbidden.status_code == 404
            for method, suffix, body in (
                ("PATCH", "", {"title": "越权写入", "version": memory["version"]}),
                ("POST", "/confirm", {"version": memory["version"]}),
                ("POST", "/retire", {"version": memory["version"]}),
            ):
                response = await client.request(
                    method,
                    "/api/v1/memories/" + memory["id"] + suffix,
                    headers=second_headers,
                    json=body,
                )
                assert response.status_code == 404

            replay_body = {
                "id": str(uuid4()),
                "project_id": str(project_id),
                "kind": "note",
                "title": "项目观察",
                "content": "只是待核实笔记。",
                "source": "合成观察",
            }
            first = await client.post("/api/v1/memories", headers=first_headers, json=replay_body)
            replay = await client.post("/api/v1/memories", headers=first_headers, json=replay_body)
            assert first.status_code == replay.status_code == 201
            assert first.json() == replay.json()
            mismatch = await client.post(
                "/api/v1/memories",
                headers=first_headers,
                json={**replay_body, "source": "不同来源"},
            )
            assert mismatch.status_code == 409
            not_rule = await client.post(
                "/api/v1/memories/" + first.json()["id"] + "/confirm",
                headers=first_headers,
                json={"version": first.json()["version"]},
            )
            assert not_rule.status_code == 422
            foreign_project = await client.patch(
                "/api/v1/memories/" + memory["id"],
                headers=first_headers,
                json={"project_id": str(uuid4()), "version": memory["version"]},
            )
            assert foreign_project.status_code == 404

            confirmed = await client.post(
                "/api/v1/memories/" + memory["id"] + "/confirm",
                headers=first_headers,
                json={"version": memory["version"]},
            )
            assert confirmed.status_code == 200
            assert confirmed.json()["state"] == "confirmed"

            stale = await client.patch(
                "/api/v1/memories/" + memory["id"],
                headers=first_headers,
                json={"content": "旧版本覆盖", "version": memory["version"]},
            )
            assert stale.status_code == 409

            corrected = await client.patch(
                "/api/v1/memories/" + memory["id"],
                headers=first_headers,
                json={
                    "content": "申请状态必须保留官方来源、核验时间和原始邮件。",
                    "version": confirmed.json()["version"],
                },
            )
            assert corrected.status_code == 200
            assert corrected.json()["state"] == "candidate"
            reconfirmed = await client.post(
                "/api/v1/memories/" + memory["id"] + "/confirm",
                headers=first_headers,
                json={"version": corrected.json()["version"]},
            )
            assert reconfirmed.status_code == 200
            assert reconfirmed.json()["state"] == "confirmed"

            restricted = await client.post(
                "/api/v1/memories",
                headers=first_headers,
                json={"kind": "note", "title": "受限", "content": "身份证号: 11010519491231002X"},
            )
            assert restricted.status_code == 422
            assert restricted.json()["error"]["code"] == "restricted_content"

            retired = await client.post(
                "/api/v1/memories/" + memory["id"] + "/retire",
                headers=first_headers,
                json={"version": reconfirmed.json()["version"]},
            )
            assert retired.status_code == 200
            listed = await client.get("/api/v1/memories", headers=first_headers)
            assert listed.status_code == 200
            assert [item["id"] for item in listed.json()["items"]] == [first.json()["id"]]
            history = await client.get(
                "/api/v1/memories",
                headers=first_headers,
                params={"include_retired": "true", "limit": 1},
            )
            assert history.status_code == 200
            assert history.json()["items"][0]["state"] == "retired"
            assert history.json()["next_cursor"]
            second_page = await client.get(
                "/api/v1/memories",
                headers=first_headers,
                params={"include_retired": "true", "cursor": history.json()["next_cursor"]},
            )
            assert [item["id"] for item in second_page.json()["items"]] == [first.json()["id"]]
            assert second_page.json()["next_cursor"] is None
            rejected = await client.post(
                "/api/v1/memories/" + memory["id"] + "/confirm",
                headers=first_headers,
                json={"version": retired.json()["version"]},
            )
            assert rejected.status_code == 422
    finally:
        await engine.dispose()
