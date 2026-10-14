import json
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from services.browser.sessions.viewer import ViewerRejected, viewer_cookie_name
from services.browser.sessions.viewer_input import ViewerInputBoundary, validate_viewer_input
from tests.browser.test_browser_viewer import (
    STEEL_FRAME,
    _app,
    _Connector,
    _steel_client,
    _token,
    _Upstream,
    _ViewerStore,
)


def key_input(key: str = "中") -> dict[str, object]:
    return {
        "type": "keyEvent",
        "pageId": "page-a",
        "event": {
            "type": "keyDown",
            "text": key,
            "key": key,
            "code": "",
            "keyCode": ord(key),
        },
    }


@pytest.mark.parametrize(
    "payload",
    [
        key_input(),
        key_input("\n"),
        key_input("\t"),
        {
            "type": "keyEvent",
            "pageId": "page-a",
            "event": {
                "type": "keyUp",
                "code": "Enter",
                "key": "Enter",
                "keyCode": 13,
            },
        },
        {
            "type": "mouseEvent",
            "pageId": "page-a",
            "event": {
                "type": "mousePressed",
                "x": 32.5,
                "y": 20,
                "button": "left",
                "clickCount": 1,
            },
        },
        {
            "type": "mouseEvent",
            "pageId": "page-a",
            "event": {
                "type": "mouseReleased",
                "x": 32.5,
                "y": 20,
                "button": "right",
                "clickCount": 2,
            },
        },
        {
            "type": "mouseEvent",
            "pageId": "page-a",
            "event": {
                "type": "mouseMoved",
                "x": 32.5,
                "y": 20,
                "button": "none",
            },
        },
        {
            "type": "mouseEvent",
            "pageId": "page-a",
            "event": {
                "type": "mouseWheel",
                "x": 32.5,
                "y": 20,
                "button": "none",
                "deltaX": 0,
                "deltaY": -100,
            },
        },
        {"type": "getSelectedText", "pageId": "page-a"},
        *[
            {"type": "navigation", "pageId": "page-a", "event": {"action": action}}
            for action in ("back", "forward", "refresh")
        ],
    ],
)
def test_pinned_native_human_events_remain_available(payload: dict[str, object]) -> None:
    normalized = json.loads(validate_viewer_input(json.dumps(payload), "page-a"))
    assert normalized["type"] == payload["type"]
    assert normalized["pageId"] == "page-a"


BAD_INPUTS: list[str | bytes | None] = [
    None,
    b"binary",
    "[]",
    "null",
    "not-json",
    "x" * 4097,
    '{"type":"getSelectedText","pageId":"other","pageId":"page-a"}',
    json.dumps(key_input() | {"pageId": "page-b"}),
    json.dumps(key_input() | {"expression": "document.querySelector('button').click()"}),
    json.dumps({"type": "closeTab", "pageId": "page-a"}),
    json.dumps({"type": "Runtime.evaluate", "pageId": "page-a", "expression": "1"}),
    *[
        json.dumps({"type": "navigation", "pageId": "page-a", "event": {"url": url}})
        for url in (
            "javascript:alert(1)",
            "file:///etc/passwd",
            "http://169.254.169.254/",
            "https://www.zhipin.com",
        )
    ],
    json.dumps(
        {
            "type": "navigation",
            "pageId": "page-a",
            "event": {"action": "refresh", "url": "https://www.zhipin.com"},
        }
    ),
    *[
        json.dumps({"type": "keyEvent", "pageId": "page-a", "event": event})
        for event in (
            {"type": "keyDown", "text": "long text", "key": "x", "code": "KeyX", "keyCode": 88},
            {"type": "keyDown", "text": "中", "key": "x", "code": "KeyX", "keyCode": 88},
            {"type": "keyDown", "text": "x", "key": "x", "code": "KeyX", "keyCode": True},
            {"type": "keyDown", "key": "x", "code": "KeyX", "keyCode": 88, "commands": ["paste"]},
        )
    ],
    *[
        json.dumps(
            {
                "type": "mouseEvent",
                "pageId": "page-a",
                "event": {
                    "type": "mousePressed",
                    "x": x,
                    "y": 10,
                    "button": "left",
                    "clickCount": 1,
                },
            }
        )
        for x in (float("nan"), float("inf"), -1, True, "10", 32768)
    ],
    json.dumps(
        {
            "type": "mouseEvent",
            "pageId": "page-a",
            "event": {
                "type": "mouseMoved",
                "x": 20,
                "y": 10,
                "button": "left",
                "clickCount": 1,
            },
        }
    ),
    json.dumps(key_input("\x00")),
    json.dumps(key_input("\ud800")),
]


@pytest.mark.parametrize("message", BAD_INPUTS)
def test_invalid_or_privileged_input_is_not_forwarded(message: str | bytes | None) -> None:
    with pytest.raises(ViewerRejected):
        validate_viewer_input(message, "page-a")


@pytest.mark.parametrize(
    "message", [b"binary", "malformed", json.dumps({"type": "closeTab", "pageId": "page-a"})]
)
def test_signed_control_ticket_cannot_forward_non_input(message: str | bytes) -> None:
    session_id = uuid4()
    key = Ed25519PrivateKey.generate()
    store = _ViewerStore()
    upstream = _Upstream()
    with (
        TestClient(
            _app(
                key,
                store,
                _steel_client(lambda _: httpx.Response(500), session_id),
                _Connector(upstream),
            )
        ) as client,
        client.websocket_connect(
            f"/internal/v1/sessions/{session_id}/cast?pageId=page-a",
            headers={
                "Origin": "https://careeract.example",
                "Cookie": f"{viewer_cookie_name(session_id)}={_token(key, session_id)}",
            },
        ) as socket,
    ):
        assert socket.receive_text() == STEEL_FRAME
        if isinstance(message, bytes):
            socket.send_bytes(message)
        else:
            socket.send_text(message)
        with pytest.raises(WebSocketDisconnect) as stopped:
            socket.receive_text()
        assert stopped.value.code == 1008
    assert upstream.sent == []
    assert store.drained and store.released


def test_input_requires_frame_and_closure_invalidates_geometry() -> None:
    boundary = ViewerInputBoundary("page-a")
    event = json.dumps(key_input())
    with pytest.raises(ViewerRejected):
        boundary.validate(event)
    boundary.observe_frame(STEEL_FRAME)
    assert boundary.validate(event)
    boundary.observe_frame(json.dumps({"type": "targetClosed"}))
    with pytest.raises(ViewerRejected):
        boundary.validate(event)


@pytest.mark.parametrize("scale,offset", [(1, 0), (1.25, 20), (2, 40)])
def test_mouse_bounds_use_upstream_css_geometry(scale: float, offset: int) -> None:
    boundary = ViewerInputBoundary("page-a")
    frame = json.loads(STEEL_FRAME)
    frame["metadata"].update(pageScaleFactor=scale, offsetTop=offset)
    boundary.observe_frame(json.dumps(frame))
    width, height = 1280 / scale, (720 - offset) / scale

    def mouse(x: float, y: float) -> str:
        return json.dumps(
            {
                "type": "mouseEvent",
                "pageId": "page-a",
                "event": {"type": "mouseMoved", "button": "none", "x": x, "y": y},
            }
        )

    assert boundary.validate(mouse(width - 0.5, height - 0.5))
    for x, y in [(width, 10), (10, height), (width + 1, height + 1)]:
        with pytest.raises(ViewerRejected):
            boundary.validate(mouse(x, y))


@pytest.mark.parametrize(
    "change",
    [
        {"deviceWidth": True},
        {"deviceHeight": float("nan")},
        {"pageScaleFactor": 0},
        {"offsetTop": 720},
        {"offsetTop": -1},
    ],
)
def test_bad_frame_clears_previously_valid_geometry(change: dict[str, object]) -> None:
    boundary = ViewerInputBoundary("page-a")
    boundary.observe_frame(STEEL_FRAME)
    frame = json.loads(STEEL_FRAME)
    frame["metadata"].update(change)
    with pytest.raises(ViewerRejected):
        boundary.observe_frame(json.dumps(frame))
    with pytest.raises(ViewerRejected):
        boundary.validate(json.dumps(key_input()))


def test_frame_from_other_page_cannot_authorize_input() -> None:
    boundary = ViewerInputBoundary("page-a")
    frame = json.loads(STEEL_FRAME)
    frame["pageId"] = "page-b"
    with pytest.raises(ViewerRejected):
        boundary.observe_frame(json.dumps(frame))
    with pytest.raises(ViewerRejected):
        boundary.validate(json.dumps(key_input()))
