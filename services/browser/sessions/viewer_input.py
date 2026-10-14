"""Allow only the pinned Steel Viewer's human input protocol.

This channel is not an Agent tool or an arbitrary CDP/JavaScript transport.
The session lease is checked separately for every forwarded event.
"""

import json
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from services.browser.sessions.viewer import ViewerRejected

MAX_INPUT_BYTES = 4096


class _InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class _MouseEvent(_InputModel):
    type: Literal["mousePressed", "mouseReleased", "mouseMoved", "mouseWheel"]
    x: float = Field(ge=0, lt=32768, allow_inf_nan=False)
    y: float = Field(ge=0, lt=32768, allow_inf_nan=False)
    button: Literal["left", "middle", "right", "none"]
    modifiers: int = Field(default=0, ge=0, le=15)
    clickCount: int | None = Field(default=None, ge=0, le=3)
    deltaX: float | None = Field(default=None, ge=-32768, le=32768, allow_inf_nan=False)
    deltaY: float | None = Field(default=None, ge=-32768, le=32768, allow_inf_nan=False)

    @model_validator(mode="after")
    def coherent_event(self) -> "_MouseEvent":
        if self.type in {"mousePressed", "mouseReleased"}:
            if self.button == "none" or self.clickCount is None:
                raise ValueError("Mouse click requires its button and count")
        elif self.button != "none" or self.clickCount is not None:
            raise ValueError("Movement must not synthesize a click")
        if (self.deltaX is not None or self.deltaY is not None) != (self.type == "mouseWheel"):
            raise ValueError("Wheel deltas belong only to wheel events")
        if self.type == "mouseWheel" and (self.deltaX is None or self.deltaY is None):
            raise ValueError("Wheel requires both deltas")
        return self


class _KeyEvent(_InputModel):
    type: Literal["keyDown", "keyUp"]
    text: str | None = Field(default=None, min_length=1, max_length=1)
    code: str = Field(max_length=64)
    key: str = Field(min_length=1, max_length=64)
    keyCode: int = Field(ge=0, le=65535)
    modifiers: int = Field(default=0, ge=0, le=15)

    @model_validator(mode="after")
    def coherent_event(self) -> "_KeyEvent":
        if self.text is not None and self.text != self.key:
            raise ValueError("Text must be the actual single key")
        for value in (self.code, self.key, self.text or ""):
            if any(
                (ord(char) < 32 and char not in "\n\t\r") or 0xD800 <= ord(char) <= 0xDFFF
                for char in value
            ):
                raise ValueError("Invalid keyboard character")
        return self


class _MouseInput(_InputModel):
    type: Literal["mouseEvent"]
    pageId: str
    event: _MouseEvent


class _KeyInput(_InputModel):
    type: Literal["keyEvent"]
    pageId: str
    event: _KeyEvent


class _SelectionInput(_InputModel):
    type: Literal["getSelectedText"]
    pageId: str


class _NavigationEvent(_InputModel):
    action: Literal["back", "forward", "refresh"]


class _NavigationInput(_InputModel):
    type: Literal["navigation"]
    pageId: str
    event: _NavigationEvent


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate input field")
        result[key] = value
    return result


def validate_viewer_input(message: str | bytes | None, page_id: str) -> str:
    """Reject binary, extra fields, wrong pages and non-input commands before forwarding.

    Human back/forward/refresh are normal toolbar actions. Arbitrary URL navigation,
    closeTab, batches and all script/CDP commands require a different product contract
    and cannot use this channel. Invalid payloads are never included in errors/logs.
    """
    if not isinstance(message, str):
        raise ViewerRejected("Viewer requires a text input event")
    try:
        if len(message.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError("Input event too large")
        payload = json.loads(message, object_pairs_hook=_unique_object)
        if not isinstance(payload, dict) or payload.get("pageId") != page_id:
            raise ValueError("Input belongs to a different page")
        kind = payload.get("type")
        model: type[_MouseInput | _KeyInput | _SelectionInput | _NavigationInput]
        if kind == "mouseEvent":
            model = _MouseInput
        elif kind == "keyEvent":
            model = _KeyInput
        elif kind == "getSelectedText":
            model = _SelectionInput
        elif kind == "navigation":
            model = _NavigationInput
        else:
            raise ValueError("Not an allowed human input event")
        validated = model.model_validate(payload)
        return validated.model_dump_json(exclude_none=True)
    except (ValueError, ValidationError, RecursionError):
        raise ViewerRejected("Viewer input rejected") from None


class ViewerInputBoundary:
    """Bind human events to the geometry actually sent by the pinned screencast.

    Never trust a client-supplied viewport. A static page need not emit repeated
    frames; retain its last geometry while this exact stream/lease remains live.
    """

    def __init__(self, page_id: str) -> None:
        self.page_id = page_id
        self.extent: tuple[float, float] | None = None

    def observe_frame(self, message: str) -> None:
        try:
            payload = json.loads(message)
        except (ValueError, RecursionError):
            return
        if not isinstance(payload, dict):
            return
        if payload.get("type") == "targetClosed":
            self.extent = None
        if "data" not in payload:
            return
        self.extent = None
        metadata = payload.get("metadata")
        if payload.get("pageId") != self.page_id or not isinstance(metadata, dict):
            raise ViewerRejected("Viewer frame is not bound to its page")
        values = [
            metadata.get(key)
            for key in ("deviceWidth", "deviceHeight", "pageScaleFactor", "offsetTop")
        ]
        numbers: list[float] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ViewerRejected("Viewer frame geometry unavailable")
            if not math.isfinite(value):
                raise ViewerRejected("Viewer frame geometry unavailable")
            numbers.append(float(value))
        width, height, scale, offset = numbers
        if not (
            0 < width <= 32768
            and 0 < height <= 32768
            and 0.05 <= scale <= 20
            and 0 <= offset < height
        ):
            raise ViewerRejected("Viewer frame geometry unavailable")
        self.extent = (width / scale, (height - offset) / scale)

    def validate(self, message: str | bytes | None) -> str:
        normalized = validate_viewer_input(message, self.page_id)
        if self.extent is None:
            raise ViewerRejected("Viewer requires its displayed page before input")
        payload = json.loads(normalized)
        if payload["type"] == "mouseEvent":
            event = payload["event"]
            if event["x"] >= self.extent[0] or event["y"] >= self.extent[1]:
                raise ViewerRejected("Viewer input is outside its displayed page")
        return normalized
