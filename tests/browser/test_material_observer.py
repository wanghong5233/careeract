"""Default boundary tests: no browser, account or network used."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest
from patchright.async_api import Page

from services.browser.sessions.site_safety import SiteRiskDetected, SiteSafetyBlocked
from services.browser.site_adapters.boss_material_observer import (
    BOSS_MATERIAL_URL,
    BossMaterialObserver,
    MaterialObservationUnavailable,
)


@pytest.fixture
def page() -> Mock:
    value = Mock(spec=Page)
    value.url = BOSS_MATERIAL_URL
    value.is_closed.return_value = False
    value.evaluate = AsyncMock(
        return_value={
            "url": BOSS_MATERIAL_URL,
            "risk": None,
            "catalog": json.dumps({"state": "empty", "materials": []}),
        }
    )
    return value


@pytest.mark.asyncio
async def test_observation_holds_both_guards_until_result_is_validated(page: Mock) -> None:
    entered: list[str] = []

    @asynccontextmanager
    async def lease() -> AsyncIterator[None]:
        entered.append("lease")
        yield
        assert entered == ["lease", "site"]
        entered.pop()

    @asynccontextmanager
    async def site() -> AsyncIterator[None]:
        assert entered == ["lease"]
        entered.append("site")
        yield

    assert (
        await BossMaterialObserver(page, lease_guard=lease, site_guard=site).observe()
    ).state == ("empty")
    assert entered == ["lease"]


@asynccontextmanager
async def guard() -> AsyncIterator[None]:
    yield


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", ["lease", "site"])
async def test_guard_denial_prevents_dom_read(page: Mock, blocked: str) -> None:
    @asynccontextmanager
    async def deny() -> AsyncIterator[None]:
        raise SiteSafetyBlocked("Synthetic stop")
        yield

    observer = BossMaterialObserver(
        page,
        lease_guard=deny if blocked == "lease" else guard,
        site_guard=deny if blocked == "site" else guard,
    )
    with pytest.raises(SiteSafetyBlocked):
        await observer.observe()
    page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path, expected",
    [("/web/passport/zp/403.html", "denied"), ("/verify", "challenge"), ("/web/user/", None)],
)
async def test_auth_url_stops_before_dom(page: Mock, path: str, expected: str | None) -> None:
    page.url = "https://www.zhipin.com" + path
    observer = BossMaterialObserver(page, lease_guard=guard, site_guard=guard)
    if expected:
        with pytest.raises(SiteRiskDetected) as error:
            await observer.observe()
        assert error.value.reason == expected
    else:
        assert (await observer.observe()).state == "needs_login"
    page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["navigation", "invalid", "oversize", "closed", "outside"])
async def test_bad_observation_is_never_empty_success(page: Mock, failure: str) -> None:
    if failure == "navigation":
        page.evaluate.return_value["url"] = BOSS_MATERIAL_URL + "?changed"
    elif failure == "invalid":
        page.evaluate.return_value["catalog"] = '{"cookie":"secret"}'
    elif failure == "oversize":
        page.evaluate.return_value["catalog"] = " " * 8193
    elif failure == "closed":
        page.is_closed.return_value = True
    else:
        page.url = "https://www.zhipin.com.attacker.invalid/web/geek/resume"
    with pytest.raises(MaterialObservationUnavailable):
        await BossMaterialObserver(page, lease_guard=guard, site_guard=guard).observe()


@pytest.mark.asyncio
async def test_page_risk_propagates_through_site_guard_for_durable_stop(page: Mock) -> None:
    page.evaluate.return_value = {"url": BOSS_MATERIAL_URL, "risk": "denied", "catalog": None}
    recorded: list[str] = []

    @asynccontextmanager
    async def site() -> AsyncIterator[None]:
        try:
            yield
        except SiteRiskDetected as error:
            recorded.append(error.reason)
            raise

    with pytest.raises(SiteRiskDetected):
        await BossMaterialObserver(page, lease_guard=guard, site_guard=site).observe()
    assert recorded == ["denied"]


@pytest.mark.asyncio
async def test_same_url_reload_during_collection_invalidates_old_document(page: Mock) -> None:
    async def capture(script: str) -> object:
        callback = page.on.call_args.args[1]
        callback(page.main_frame)
        return {
            "url": BOSS_MATERIAL_URL,
            "risk": None,
            "catalog": json.dumps({"state": "empty", "materials": []}),
        }

    page.evaluate.side_effect = capture
    with pytest.raises(MaterialObservationUnavailable):
        await BossMaterialObserver(page, lease_guard=guard, site_guard=guard).observe()
    page.remove_listener.assert_called_once()
