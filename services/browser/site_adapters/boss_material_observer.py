"""Unassembled, read-only attachment observation of an already owned Patchright page.

No browser creation, navigation, Profile restore, network calls or input. Both guards
are mandatory: the existing executor lease, then the durable per-user/site stop.
"""

import asyncio
from urllib.parse import urlsplit

from patchright.async_api import Error, Frame, Page
from pydantic import BaseModel, ConfigDict, ValidationError

from services.browser.sessions.site_safety import RiskReason, SiteRiskDetected
from services.browser.sessions.ui_input import ActionGuard
from services.browser.site_adapters.boss import BossPageState, boss_auth_page_state
from services.browser.site_adapters.boss_materials import (
    _VISIBLE_TEXT,
    BOSS_MATERIAL_CATALOG,
    BossMaterialCatalog,
    parse_material_catalog,
)

BOSS_MATERIAL_URL = "https://www.zhipin.com/web/geek/resume"

# The fixed inspector returns only a risk category and bounded catalog metadata.
# Page instructions cannot supply code, tools, navigation, or authorization.
_OBSERVATION = (
    "(() => {"
    + _VISIBLE_TEXT
    + r"""
    const elements = Array.from(document.querySelectorAll('body *'));
    if (elements.length > 4096) return {url: location.href, risk: null, catalog: null};
    for (const element of elements) {
        const text = visibleText(element, false);
        if (!text || text.length > 500) continue;
        let risk = null;
        if (/访问受限|禁止访问|访问被拒绝|access denied|forbidden/i.test(text)) risk = 'denied';
        else if (/安全验证|验证码|完成验证|captcha/i.test(text)
            || /verify you are human|security verification/i.test(text))
            risk = 'challenge';
        else if (/(?:请求|操作|访问)过于频繁|稍后再试|too many requests/i.test(text))
            risk = 'rate_limited';
        else if (/(?:账号|账户|访问|环境)异常|异常访问|unusual activity/i.test(text))
            risk = 'abnormal';
        if (risk) return {url: location.href, risk, catalog: null};
    }
    return {url: location.href, risk: null, catalog: """
    + BOSS_MATERIAL_CATALOG
    + "}; })()"
)


class _Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    url: str
    risk: RiskReason | None
    catalog: str | None


class MaterialObservationUnavailable(Exception):
    """No trustworthy current material observation; no implicit retry or input."""


class BossMaterialObserver:
    def __init__(self, page: Page, *, lease_guard: ActionGuard, site_guard: ActionGuard) -> None:
        self._page = page
        self._lease_guard = lease_guard
        self._site_guard = site_guard

    def _check_url(self, url: str) -> bool:
        if self._page.is_closed():
            raise MaterialObservationUnavailable("Owned page closed")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "www.zhipin.com":
            raise MaterialObservationUnavailable("Page outside material site")
        state = boss_auth_page_state(url)
        if state == BossPageState.RISK:
            raise SiteRiskDetected(
                "denied" if parsed.path.lower() == "/web/passport/zp/403.html" else "challenge"
            )
        if state == BossPageState.NEEDS_LOGIN:
            return False
        if url != BOSS_MATERIAL_URL:
            raise MaterialObservationUnavailable("Page outside attachment manager")
        return True

    async def observe(self) -> BossMaterialCatalog:
        changed = False

        def navigated(frame: Frame) -> None:
            nonlocal changed
            if frame == self._page.main_frame:
                changed = True

        try:
            async with asyncio.timeout(5), self._lease_guard(), self._site_guard():
                if not self._check_url(self._page.url):
                    return BossMaterialCatalog("needs_login")
                self._page.on("framenavigated", navigated)
                try:
                    observation = _Observation.model_validate(
                        await self._page.evaluate(_OBSERVATION)
                    )
                finally:
                    self._page.remove_listener("framenavigated", navigated)
                if observation.risk is not None:
                    raise SiteRiskDetected(observation.risk)
                # Recheck both in-page and driver URLs: navigation during collection
                # cannot leave an accepted catalog from an old document.
                if (
                    changed
                    or not self._check_url(self._page.url)
                    or not self._check_url(observation.url)
                ):
                    raise MaterialObservationUnavailable("Page changed during observation")
                if observation.catalog is None:
                    raise MaterialObservationUnavailable("Visible observation exceeds bounds")
                result = parse_material_catalog(observation.catalog)
            return result
        except (Error, TimeoutError, ValidationError, ValueError):
            # Never echo page data or convert a transport/schema failure to empty.
            raise MaterialObservationUnavailable("Material observation unavailable") from None
