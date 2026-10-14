"""Bounded normal input; not registered as an Agent tool or business endpoint.

The caller supplies the owned Patchright page and the existing transactional lease
guard. This adapter never creates/navigates a page or evaluates caller-provided code.
"""

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from time import monotonic
from typing import Literal

from patchright.async_api import ElementHandle, Error, Locator, Page

from services.browser.sessions.authentication import CommandRejected
from services.browser.sessions.lease import LeaseConflict

InputRole = Literal["button", "textbox", "link"]
ActionGuard = Callable[[], AbstractAsyncContextManager[None]]

# Fixed, read-only DOM geometry. No component state, mutation or hidden data extraction.
_TARGET_STATE = """element => {
    const rect = element.getBoundingClientRect();
    const x = rect.x + rect.width / 2, y = rect.y + rect.height / 2;
    let opaque = true;
    for (let node = element; node; node = node.parentElement) {
        if (Number(getComputedStyle(node).opacity) === 0) opaque = false;
    }
    const hit = document.elementFromPoint(x, y);
    return {
        in_viewport: rect.width > 0 && rect.height > 0 && rect.x >= 0 && rect.y >= 0 &&
            rect.right <= innerWidth && rect.bottom <= innerHeight,
        unobscured: opaque && hit !== null && (hit === element || element.contains(hit))
    };
}"""


class UIInputRejected(Exception):
    """No normal input was dispatched; observe again or request human handling."""


class UIInputUncertain(Exception):
    """Input may have reached the page; do not replay a business write."""


@dataclass
class ObservedTarget:
    locator: Locator
    element: ElementHandle
    role: InputRole
    observed_at: float
    adapter: object
    consumed: bool = False


class NormalUIInput:
    def __init__(self, page: Page, *, expected_url: str, action_guard: ActionGuard) -> None:
        self._page = page
        self._url = expected_url
        self._guard = action_guard
        self._identity = object()
        self._uncertain = False
        # Keep framework waits within the signed command / short lease boundary.
        self._timeout_ms = 1500
        self._fresh_seconds = 3.0

    def _check_page(self) -> None:
        if self._uncertain or self._page.is_closed() or self._page.url != self._url:
            raise UIInputRejected("Page no longer matches the observed task")

    async def _check_target(self, target: ObservedTarget, *, check_fresh: bool = True) -> None:
        self._check_page()
        if target.adapter is not self._identity or (
            check_fresh and monotonic() - target.observed_at > self._fresh_seconds
        ):
            raise UIInputRejected("Target observation is no longer current")
        if await target.locator.count() != 1:
            raise UIInputRejected("Target is no longer unique")
        current = await target.locator.element_handle(timeout=self._timeout_ms)
        if current is None or not await target.element.evaluate(
            "(element, current) => element === current", current
        ):
            raise UIInputRejected("Observed element was replaced")
        if not await target.element.is_visible() or not await target.element.is_enabled():
            raise UIInputRejected("Target is not visible and enabled")
        geometry = await target.element.evaluate(_TARGET_STATE)
        if geometry["in_viewport"] is not True or geometry["unobscured"] is not True:
            raise UIInputRejected("Target is outside the viewport or obscured")
        self._check_page()

    async def observe(self, role: InputRole, name: str) -> ObservedTarget:
        try:
            async with asyncio.timeout(5), self._guard():
                self._check_page()
                locator = self._page.get_by_role(role, name=name, exact=True)
                if await locator.count() != 1:
                    raise UIInputRejected("Target must have one exact visible role and name")
                element = await locator.element_handle(timeout=self._timeout_ms)
                if element is None:
                    raise UIInputRejected("Target is not attached")
                target = ObservedTarget(locator, element, role, monotonic(), self._identity)
                await self._check_target(target)
                return target
        except (Error, TimeoutError):
            raise UIInputRejected("Target observation unavailable") from None

    async def click(self, target: ObservedTarget) -> None:
        await self._input(target, text=None)

    async def type_text(self, target: ObservedTarget, text: str) -> None:
        # Newlines/control characters can submit or change focus. Multiline/shortcuts
        # require a separate reviewed operation; never accept a model's key sequence.
        if (
            target.role != "textbox"
            or len(text) > 2000
            or any(ord(char) < 32 or ord(char) == 127 for char in text)
        ):
            raise UIInputRejected("Only bounded single-line textbox input is supported")
        await self._input(target, text=text)

    async def _input(self, target: ObservedTarget, *, text: str | None) -> None:
        if target.consumed:
            raise UIInputRejected("Target observation was already consumed")
        target.consumed = True
        dispatched = False
        completed = False
        try:
            async with asyncio.timeout(5), self._guard():
                await self._check_target(target)
                if text is not None and not await target.element.is_editable():
                    raise UIInputRejected("Textbox is not editable")
                # Use the captured element, not a locator which could silently retarget.
                # Patchright supplies actionability/hit-testing; force is never enabled.
                dispatched = True
                await target.element.click(timeout=self._timeout_ms)
                if text is not None:
                    for key in ("ControlOrMeta+A", "Backspace"):
                        await self._check_focus(target)
                        await self._page.keyboard.press(key)
                    for char in text:
                        await self._check_focus(target)
                        await self._page.keyboard.type(char)
                    await self._check_focus(target)
                    if await target.element.input_value(timeout=self._timeout_ms) != text:
                        raise UIInputUncertain("Textbox readback did not match input")
                self._check_page()
            completed = True
        except (Error, UIInputRejected, UIInputUncertain, TimeoutError):
            if dispatched:
                self._uncertain = True
                raise UIInputUncertain(
                    "Input outcome requires reconciliation; do not replay"
                ) from None
            raise UIInputRejected("Target no longer admits normal input") from None
        except (CommandRejected, LeaseConflict):
            if dispatched:
                self._uncertain = True
                raise UIInputUncertain("Input authorization ended during execution") from None
            raise
        finally:
            # Cancellation or an unexpected guard/transport failure cannot prove
            # that input was undelivered. Preserve the error; never admit replay.
            if dispatched and not completed:
                self._uncertain = True

    async def _check_focus(self, target: ObservedTarget) -> None:
        await self._check_target(target, check_fresh=False)
        if not await target.element.evaluate("element => document.activeElement === element"):
            raise UIInputRejected("Textbox lost focus")
