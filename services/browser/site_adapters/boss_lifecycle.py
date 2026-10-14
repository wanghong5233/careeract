from collections.abc import Awaitable, Callable
from uuid import UUID

from services.browser.sessions.context import BrowserContext, BrowserContextRejected
from services.browser.sessions.profiles import PostgresBrowserProfileStore
from services.browser.sessions.site_lifecycle import (
    ProfiledSiteLifecycle,
    SiteLifecycleUnavailable,
    SiteSessionLifecycle,
)
from services.browser.site_adapters.boss_context import BossContextReader, BossContextUnavailable
from services.browser.site_adapters.boss_login import BossLoginUnavailable


def boss_site_lifecycles(
    *,
    profiles: PostgresBrowserProfileStore | None,
    navigator: Callable[[UUID], Awaitable[None]] | None,
    reader: Callable[[UUID], BossContextReader],
    read_navigator: Callable[[UUID], Awaitable[None]] | None = None,
) -> dict[str, SiteSessionLifecycle]:
    async def prepare(session_id: UUID) -> None:
        if navigator is None:
            return
        try:
            await navigator(session_id)
        except BossLoginUnavailable:
            raise SiteLifecycleUnavailable("Site navigation unavailable") from None

    async def capture(session_id: UUID) -> BrowserContext | None:
        try:
            captured = await reader(session_id).storage_state()
            if (
                profiles is None
                or not isinstance(captured, dict)
                or captured.get("authenticated") is not True
            ):
                return None
            return BrowserContext.from_playwright(captured, profiles.scope)
        except (BossContextUnavailable, BrowserContextRejected):
            raise SiteLifecycleUnavailable("Site context capture unavailable") from None

    login = ProfiledSiteLifecycle(
        profiles,
        prepare=prepare,
        capture=capture,
        actions=frozenset({"create", "release", "finish", "forget"}),
    )

    async def prepare_read(session_id: UUID) -> None:
        if read_navigator is None:
            raise SiteLifecycleUnavailable("Read navigation is not configured")
        try:
            await read_navigator(session_id)
        except BossLoginUnavailable:
            raise SiteLifecycleUnavailable("Read navigation unavailable") from None

    reading = ProfiledSiteLifecycle(profiles, prepare=prepare_read)
    viewing = ProfiledSiteLifecycle(profiles, prepare=prepare, capture=capture)
    return {
        "boss-login": login,
        "boss-read": reading,
        "boss-reply": reading,
        "saved-login-viewer": viewing,
    }
