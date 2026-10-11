from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import UUID

from services.browser.sessions.authentication import LifecycleAction
from services.browser.sessions.context import BrowserContext
from services.browser.sessions.profiles import PostgresBrowserProfileStore


class SiteLifecycleUnavailable(Exception):
    pass


class SiteSessionLifecycle(Protocol):
    actions: frozenset[LifecycleAction]

    async def restore(self, user_id: str) -> BrowserContext | None: ...

    async def prepare(self, session_id: UUID) -> None: ...

    async def save(self, user_id: str, session_id: UUID) -> bool: ...

    async def forget(self, user_id: str, session_id: UUID) -> None: ...


class ProfiledSiteLifecycle:
    def __init__(
        self,
        profiles: PostgresBrowserProfileStore | None,
        *,
        prepare: Callable[[UUID], Awaitable[None]] | None = None,
        capture: Callable[[UUID], Awaitable[BrowserContext | None]] | None = None,
        actions: frozenset[LifecycleAction] = frozenset({"create", "release"}),
    ) -> None:
        self.profiles = profiles
        self.prepare_page = prepare
        self.capture = capture
        self.actions = actions

    async def restore(self, user_id: str) -> BrowserContext | None:
        current = await self.profiles.current(user_id) if self.profiles is not None else None
        return current[1] if current is not None else None

    async def prepare(self, session_id: UUID) -> None:
        if self.prepare_page is not None:
            await self.prepare_page(session_id)

    async def save(self, user_id: str, session_id: UUID) -> bool:
        if self.profiles is None or self.capture is None:
            return False
        snapshot = await self.capture(session_id)
        if snapshot is None:
            return False
        current = await self.profiles.current(user_id)
        if current is None:
            await self.profiles.create(user_id, snapshot)
        else:
            await self.profiles.save(
                user_id, current[0].id, snapshot, expected_version=current[0].version
            )
        return True

    async def forget(self, user_id: str, session_id: UUID) -> None:
        if self.profiles is None:
            raise SiteLifecycleUnavailable("Site profile removal is unavailable")
        await self.profiles.forget_released_session(user_id, session_id)
