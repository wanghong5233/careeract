import json
from uuid import uuid4

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from services.api.domain.privacy import RestrictedContent, ensure_career_content

AGENT_BODY_LIMIT = 262_144
PRODUCT_BODY_LIMIT = 1_048_576


def json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_value: str) -> object:
    raise ValueError("Non-finite JSON number")


def validate_structure(value: object) -> None:
    pending = [(value, 0)]
    count = 0
    while pending:
        current, depth = pending.pop()
        count += 1
        if depth > 32 or count > 20_000:
            raise ValueError("JSON structure exceeds limit")
        if isinstance(current, dict):
            pending.extend((child, depth + 1) for child in current.values())
        elif isinstance(current, list):
            pending.extend((child, depth + 1) for child in current)


def is_text_run(value: object) -> bool:
    if not isinstance(value, dict) or set(value) - {
        "threadId",
        "runId",
        "parentRunId",
        "messages",
        "tools",
        "context",
        "state",
        "forwardedProps",
    }:
        return False
    if any(
        value.get(field) not in (None, {}, [])
        for field in (
            "tools",
            "context",
            "state",
            "forwardedProps",
        )
    ):
        return False
    messages = value.get("messages")
    if not isinstance(messages, list) or not messages:
        return False
    for message in messages:
        if (
            not isinstance(message, dict)
            or set(message) - {"id", "role", "content", "name"}
            or message.get("role") not in ("user", "assistant")
        ):
            return False
        content = message.get("content")
        if isinstance(content, str):
            continue
        if not isinstance(content, list) or not content:
            return False
        for part in content:
            if (
                not isinstance(part, dict)
                or set(part) != {"type", "text"}
                or part.get("type") != "text"
                or not isinstance(part.get("text"), str)
            ):
                return False
        ensure_career_content("\n".join(part["text"] for part in content))
    return bool(messages[-1].get("role") == "user")


class PrivacyBoundaryMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        is_agent = scope["type"] == "http" and scope["path"].startswith("/agui")
        is_product = scope["type"] == "http" and scope["path"].startswith("/api/v1/")
        if not (is_agent or is_product) or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if (
            headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json"
            or headers.get("content-encoding", "identity").lower() != "identity"
        ):
            await self.reject(
                scope, receive, send, 415, "unsupported_content", "当前仅接收 JSON 文本。"
            )
            return
        limit = AGENT_BODY_LIMIT if is_agent else PRODUCT_BODY_LIMIT
        body = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            chunk = event.get("body", b"")
            if len(body) + len(chunk) > limit:
                await self.reject(
                    scope, receive, send, 413, "content_too_large", "内容过大，请精简后重试。"
                )
                return
            body.extend(chunk)
            if not event.get("more_body", False):
                break
        try:
            payload = json.loads(
                body.decode("utf-8"), object_pairs_hook=json_object, parse_constant=reject_constant
            )
            validate_structure(payload)
        except (ValueError, RecursionError):
            await self.reject(
                scope, receive, send, 400, "invalid_json", "请求内容不是有效的 JSON。"
            )
            return
        try:
            ensure_career_content(payload)
            text_run_allowed = is_text_run(payload) if is_agent else True
        except RestrictedContent as error:
            await self.reject(scope, receive, send, 422, "restricted_content", str(error))
            return
        if not text_run_allowed:
            await self.reject(
                scope,
                receive,
                send,
                422,
                "unsupported_agent_input",
                "伙伴当前仅接收文本；附件、客户端工具和自定义上下文尚未开放。",
            )
            return

        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def reject(
        scope: Scope, receive: Receive, send: Send, status: int, code: str, message: str
    ) -> None:
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        response = JSONResponse(
            {"error": {"code": code, "message": message, "request_id": request_id}},
            status_code=status,
            headers={"Cache-Control": "no-store", "X-Request-ID": request_id},
        )
        await response(scope, receive, send)
