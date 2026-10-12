from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from services.api.application.ports.browser_control import (
    BrowserControlConflict,
    BrowserControlRejected,
    BrowserControlUncertain,
)
from services.api.infrastructure.boss_page import BossPageClient
from services.api.infrastructure.browser_control import BrowserCommandSigner
from tests.api.test_browser_control import control_context


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        None,
        "timeout",
        "redirect",
        "rejected",
        "conflict",
        "server",
        "malformed",
        "wrong-session",
        "raw-html",
        "unknown-sender",
        "coerced-unread",
        "offsite",
        "invalid-port",
        "offsite-conversation",
        "oversize",
        "expired",
    ],
)
async def test_page_client_validates_scope_binding_and_nested_response(failure: str | None) -> None:
    key = Ed25519PrivateKey.generate()
    context = replace(control_context(), owner_id="boss-page-reader")
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == f"/internal/v1/sessions/{context.session_id}/boss/page"
        claims = jwt.decode(
            request.headers["Authorization"].removeprefix("Bearer "),
            key.public_key(),
            algorithms=["EdDSA"],
            audience="careeract-browser",
        )
        assert claims["action"] == "snapshot" and claims["lease_id"] is None
        assert claims["owner_id"] == "boss-page-reader"
        assert claims["task_id"] == str(context.task_id)
        assert claims["authorization_id"] == str(context.authorization_id)
        if failure == "timeout":
            raise httpx.ReadTimeout("private synthetic text", request=request)
        if failure == "redirect":
            return httpx.Response(307, headers={"Location": "http://untrusted.invalid"})
        if failure in {"rejected", "conflict", "server"}:
            return httpx.Response(
                {"rejected": 403, "conflict": 409, "server": 503}[failure],
                text="private synthetic text",
            )
        if failure == "malformed":
            return httpx.Response(200, text="private synthetic text")
        if failure == "oversize":
            return httpx.Response(
                200, content=b" " * (512 * 1024 + 1), headers={"Content-Type": "application/json"}
            )
        if failure == "expired":
            object.__setattr__(
                context, "authorization_expires_at", datetime.now(UTC) - timedelta(seconds=1)
            )
        message = {
            "message_id": "synthetic-message",
            "sender": "human" if failure == "unknown-sender" else "recruiter",
            "content": "private synthetic text",
            "sent_at": None,
        }
        page = {
            "url": "https://www.zhipin.com/web/geek/chat",
            "title": "BOSS",
            "kind": "conversations",
            "state": "ready",
            "jobs": [],
            "signals": ["conversation_data"],
            "conversations": [
                {
                    "conversation_id": "synthetic-conversation",
                    "recruiter_name": None,
                    "company": None,
                    "job_title": None,
                    "last_message": "private synthetic text",
                    "unread": "false" if failure == "coerced-unread" else False,
                    "url": "https://untrusted.invalid"
                    if failure == "offsite-conversation"
                    else None,
                }
            ],
            "messages": [message],
        }
        if failure == "raw-html":
            message["html"] = "private synthetic text"
        if failure == "offsite":
            page["url"] = "https://untrusted.invalid"
        if failure == "invalid-port":
            page["url"] = "https://www.zhipin.com:invalid/"
        return httpx.Response(
            200,
            json={
                "session_id": str(uuid4() if failure == "wrong-session" else context.session_id),
                "page": page,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://browser"
    ) as client:
        adapter = BossPageClient(client, BrowserCommandSigner(key))
        if failure is None:
            result = await adapter.read_boss_page(context)
            assert result.messages[0].sender == "recruiter"
            assert result.conversations[0].unread is False
            assert "private" not in repr(result) and "private" not in repr(result.messages)
        else:
            error = {
                "rejected": BrowserControlRejected,
                "conflict": BrowserControlConflict,
            }.get(failure, BrowserControlUncertain)
            with pytest.raises(error) as caught:
                await adapter.read_boss_page(context)
            assert "private" not in str(caught.value)
        assert calls == 1
        with pytest.raises(BrowserControlRejected):
            await adapter.read_boss_page(replace(context, owner_id="saved-login-viewer"))
        assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_target", [False, True, "resume"])
async def test_selected_conversation_is_signed_and_response_cannot_switch_recipient(
    wrong_target: bool | str,
) -> None:
    key = Ed25519PrivateKey.generate()
    context = replace(control_context(), owner_id="boss-page-reader", conversation_id="thread-1")

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/boss/conversation")
        claims = jwt.decode(
            request.headers["Authorization"].removeprefix("Bearer "),
            key.public_key(),
            algorithms=["EdDSA"],
            audience="careeract-browser",
        )
        assert claims["conversation_id"] == "thread-1" and claims["action"] == "conversation"
        return httpx.Response(
            200,
            json={
                "session_id": str(context.session_id),
                "page": {
                    "url": "https://www.zhipin.com/web/geek/chat",
                    "title": "Synthetic",
                    "jobs": [],
                    "signals": [],
                    "kind": "conversations",
                    "state": "ready",
                    "conversations": [
                        {
                            "conversation_id": "thread-1",
                            "recruiter_name": None,
                            "company": None,
                            "job_title": None,
                            "last_message": None,
                            "unread": False,
                            "url": None,
                        }
                    ],
                    "messages": [
                        {
                            "conversation_id": "other-thread"
                            if wrong_target is True
                            else "thread-1",
                            "message_id": "123",
                            "sender": "recruiter",
                            "content": "Synthetic",
                            "sent_at": None,
                        }
                    ],
                    "resume_control": {
                        "conversation_id": "other-thread"
                        if wrong_target == "resume"
                        else "thread-1",
                        "state": "unavailable",
                        "attachment_reported": False,
                    },
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://browser"
    ) as client:
        reader = BossPageClient(client, BrowserCommandSigner(key))
        if wrong_target:
            with pytest.raises(BrowserControlUncertain):
                await reader.read_boss_page(context)
        else:
            assert (await reader.read_boss_page(context)).messages[0].conversation_id == "thread-1"
