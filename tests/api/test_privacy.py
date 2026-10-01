import json
from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from ag_ui.core import RunAgentInput
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Request
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from services.api.app.factory import create_app
from services.api.application.context import ActorContext
from services.api.application.ports.profiles import ProfileRepository
from services.api.application.ports.projects import ProjectRepository
from services.api.application.profiles import ProfileService
from services.api.application.projects import ProjectService
from services.api.domain.privacy import RestrictedContent, ensure_career_content
from services.api.domain.profile import ProfileContent, ProfileEntry
from services.api.infrastructure.privacy import AGENT_BODY_LIMIT
from tests.api.test_health import FakeAgentRuntime, build_settings, create_token, use_signing_key

SYNTHETIC_NUMBER = "000000" + "20000101" + "0000"
SYNTHETIC_CREDENTIAL = "password=" + "SYNTHETIC_NOT_A_REAL_SECRET"


def text_run(text: str) -> dict[str, object]:
    return {
        "threadId": str(uuid4()),
        "runId": str(uuid4()),
        "messages": [{"id": str(uuid4()), "role": "user", "content": text}],
        "tools": [],
        "context": [],
        "state": {},
        "forwardedProps": {},
    }


class RecordingRuntime(FakeAgentRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

        @self.app.post("/agui")
        async def run(_request: Request, run_input: RunAgentInput) -> StreamingResponse:
            self.calls += 1

            async def stream() -> AsyncIterator[str]:
                yield 'data: {"type":"RUN_STARTED","threadId":"test","runId":"test"}\n\n'
                yield 'data: {"type":"RUN_FINISHED","threadId":"test","runId":"test"}\n\n'

            return StreamingResponse(stream(), media_type="text/event-stream")


@pytest.mark.parametrize(
    "content",
    [
        SYNTHETIC_NUMBER,
        "我的号码是" + SYNTHETIC_NUMBER + "请填写",
        " ".join(SYNTHETIC_NUMBER),
        "".join(chr(ord(character) + 65248) for character in SYNTHETIC_NUMBER),
        "\u200b".join(SYNTHETIC_NUMBER),
        {"notes": [{"other": int("999999" + "20000101" + "0000")}]},
        {"notes": {"otp": 123456}},
        {"credentials": {"secret": "SYNTHETIC_NOT_A_REAL_SECRET"}},
        {"rules": SYNTHETIC_CREDENTIAL},
        {"evidence": "sk-" + "synthetic_example_" * 3},
    ],
)
def test_restricted_content_never_echoes_values(content: object) -> None:
    with pytest.raises(RestrictedContent) as failure:
        ensure_career_content(content)
    assert SYNTHETIC_NUMBER not in str(failure.value)
    assert "SYNTHETIC_NOT_A_REAL_SECRET" not in str(failure.value)


def test_career_text_and_privacy_discussion_remain_usable() -> None:
    ensure_career_content(
        {
            "goal": "准备华为机考，完成 150 道题；秋招 2026-10-01 开始。",
            "rules": "不要保存身份证号码、密码或验证码。提交申请前人工确认。",
            "details": "Python / PostgreSQL；提升接口效率 35%，身份证由本人填写。",
            "reference": str(uuid4()),
            "numeric_uuid": "00000000-0000-0000-0000-000000000001",
            "email": "synthetic@example.invalid",
            "phone": "10000000000",
        }
    )


async def test_use_cases_guard_writes_from_non_http_callers() -> None:
    project_repository = AsyncMock()
    profile_repository = AsyncMock()
    projects = ProjectService(cast(ProjectRepository, project_repository))
    profiles = ProfileService(cast(ProfileRepository, profile_repository))
    actor = ActorContext("synthetic-user", str(uuid4()))
    with pytest.raises(RestrictedContent):
        await projects.create(actor, title="测试项目", purpose=SYNTHETIC_NUMBER, status="planned")
    with pytest.raises(RestrictedContent):
        await projects.update(
            actor,
            uuid4(),
            title=None,
            purpose=SYNTHETIC_CREDENTIAL,
            status=None,
            expected_version=uuid4(),
        )
    with pytest.raises(RestrictedContent):
        await profiles.confirm(
            actor,
            ProfileContent(experience=(ProfileEntry(title="实习", evidence=SYNTHETIC_NUMBER),)),
            None,
            confirmed=True,
        )
    project_repository.create.assert_not_called()
    project_repository.update.assert_not_called()
    profile_repository.save_confirmed.assert_not_called()
    await projects.create(actor, title="求职项目", purpose="完成面试准备", status="planned")
    await profiles.confirm(actor, ProfileContent(goals="工程岗位"), None, confirmed=True)
    project_repository.create.assert_awaited_once()
    profile_repository.save_confirmed.assert_awaited_once()


def test_authenticated_boundary_blocks_before_runtime_or_repository(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    runtime = RecordingRuntime()
    app = create_app(build_settings(), lambda _settings: runtime)
    project_repository, profile_repository = AsyncMock(), AsyncMock()
    app.state.project_service = ProjectService(cast(ProjectRepository, project_repository))
    app.state.profile_service = ProfileService(cast(ProfileRepository, profile_repository))
    headers = {"Authorization": "Bearer " + create_token(private_key)}
    with TestClient(app) as client:
        requests = [
            ("/agui", text_run(SYNTHETIC_NUMBER), "POST"),
            ("/agui", {**text_run("普通内容"), "state": {"data": SYNTHETIC_CREDENTIAL}}, "POST"),
            ("/api/v1/projects", {"title": "项目", "purpose": SYNTHETIC_NUMBER}, "POST"),
            (
                "/api/v1/projects/" + str(uuid4()),
                {"purpose": SYNTHETIC_CREDENTIAL, "version": str(uuid4())},
                "PATCH",
            ),
            (
                "/api/v1/profile",
                {"content": {"goals": SYNTHETIC_NUMBER}, "version": None, "confirmed": True},
                "PUT",
            ),
        ]
        for path, payload, method in requests:
            response = client.request(method, path, headers=headers, json=payload)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "restricted_content"
            assert response.headers["cache-control"] == "no-store"
            assert SYNTHETIC_NUMBER not in response.text
            assert "SYNTHETIC_NOT_A_REAL_SECRET" not in response.text
        assert runtime.calls == 0
        assert not project_repository.mock_calls
        assert not profile_repository.mock_calls
        split_content = text_run("ignored")
        split_content["messages"] = [
            {
                "id": str(uuid4()),
                "role": "user",
                "content": [
                    {"type": "text", "text": SYNTHETIC_NUMBER[:9]},
                    {"type": "text", "text": SYNTHETIC_NUMBER[9:]},
                ],
            }
        ]
        split_response = client.post("/agui", headers=headers, json=split_content)
        assert split_response.status_code == 422
        assert split_response.json()["error"]["code"] == "restricted_content"
        assert runtime.calls == 0
        response = client.post("/agui", headers=headers, json=text_run("整理我的实习经历"))
        assert response.status_code == 200
        assert "RUN_FINISHED" in response.text
        assert runtime.calls == 1
    assert SYNTHETIC_NUMBER not in caplog.text
    assert "SYNTHETIC_NOT_A_REAL_SECRET" not in caplog.text


@pytest.mark.parametrize(
    "changes",
    [
        {"state": {"background": "Unapproved"}},
        {"context": [{"description": "Private", "value": "Unapproved"}]},
        {"tools": [{"name": "read_files", "description": "Read", "parameters": {}}]},
        {"forwardedProps": {"dependencies": "Unapproved"}},
        {"messages": [{"id": "test", "role": "tool", "content": "Unapproved"}]},
        {
            "messages": [
                {
                    "id": "test",
                    "role": "user",
                    "content": [
                        {
                            "type": "binary",
                            "mimeType": "image/png",
                            "url": "https://example.invalid/image",
                        }
                    ],
                }
            ]
        },
        {
            "messages": [
                {
                    "id": "test",
                    "role": "assistant",
                    "content": "text",
                    "toolCalls": [
                        {"id": "test", "function": {"name": "secret", "arguments": "{}"}}
                    ],
                }
            ]
        },
        {"extra": "Unapproved"},
    ],
)
def test_unopened_agent_channels_are_rejected(
    changes: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    runtime = RecordingRuntime()
    app = create_app(build_settings(), lambda _settings: runtime)
    with TestClient(app) as client:
        response = client.post(
            "/agui",
            headers={"Authorization": "Bearer " + create_token(private_key)},
            json=text_run("整理职业目标") | changes,
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_agent_input"
    assert runtime.calls == 0


async def test_chunked_bodies_and_malformed_inputs_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, private_key)
    runtime = RecordingRuntime()
    app = create_app(build_settings(), lambda _settings: runtime)
    headers = {
        "Authorization": "Bearer " + create_token(private_key),
        "Content-Type": "application/json",
    }

    async def chunks() -> AsyncIterator[bytes]:
        for _index in range(5):
            yield b"x" * (AGENT_BODY_LIMIT // 4)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        oversized = await client.post("/agui", headers=headers, content=chunks())
        assert oversized.status_code == 413
        for body in (
            b'{"messages": [], "messages": []}',
            b'{"state": NaN}',
            b'{"messages": "SYNTHETIC_PRIVATE_CONTENT"',
            b"[" * 40 + b"]" * 40,
            b"\xff",
        ):
            response = await client.post("/agui", headers=headers, content=body)
            assert response.status_code == 400
            assert "SYNTHETIC_PRIVATE_CONTENT" not in response.text
        media = await client.post(
            "/agui", headers=headers | {"Content-Type": "image/png"}, content=b"synthetic"
        )
        assert media.status_code == 415
        compressed = await client.post(
            "/agui", headers=headers | {"Content-Encoding": "gzip"}, content=b"synthetic"
        )
        assert compressed.status_code == 415
        unauthorized = await client.post("/agui", content=SYNTHETIC_NUMBER)
        assert unauthorized.status_code == 401
        invalid_schema = await client.post(
            "/agui",
            headers=headers,
            json=text_run("普通内容") | {"threadId": {}},
        )
        assert invalid_schema.status_code == 422
        assert invalid_schema.json()["error"]["code"] == "invalid_request"
        assert invalid_schema.headers["cache-control"] == "no-store"
        multipart_text = text_run("ignored")
        multipart_text["messages"] = [
            {
                "id": str(uuid4()),
                "role": "user",
                "content": [
                    {"type": "text", "text": "整理职业背景"},
                    {"type": "text", "text": "保留事实依据"},
                ],
            }
        ]
        allowed = await client.post("/agui", headers=headers, content=json.dumps(multipart_text))
        assert allowed.status_code == 200
    assert runtime.calls == 1
