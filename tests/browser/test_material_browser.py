"""Opt-in real driver/geometry and DB tests, entirely synthetic intercepted HTML.

All requests are fulfilled/aborted locally in the isolated test browser. No login,
Profile, BOSS network request or external write occurs, despite the fixture URL.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from patchright.async_api import Page
from sqlalchemy import text

from services.browser.sessions.site_safety import (
    PostgresSiteSafetyStore,
    RiskReason,
    SiteRiskDetected,
    SiteSafetyBlocked,
)
from services.browser.site_adapters.boss_material_observer import (
    BOSS_MATERIAL_URL,
    BossMaterialObserver,
)
from services.browser.site_adapters.boss_profile import BOSS_SCOPE
from tests.browser.test_ui_input import LeaseHarness
from tests.browser.test_ui_input import database_url as database_url
from tests.browser.test_ui_input import lease as lease
from tests.browser.test_ui_input import page as page

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_NORMAL_INPUT_TESTS") != "1",
    reason="Opt-in isolated synthetic Patchright/geometry acceptance",
)

HTML = """<!doctype html><meta charset="utf-8">
<style>body {font:16px sans-serif;padding:20px} p {margin:16px 0}</style>
<section id="manager"><h2>附件管理</h2><p id="count">文件(1/3)</p>
<article id="row"><span id="filename">Synthetic.pdf</span>
<span id="size">376.1KB</span><span id="revision">2026.10.14 09:30</span></article></section>
"""


@asynccontextmanager
async def guard() -> AsyncIterator[None]:
    yield


@pytest.fixture
async def material_page(page: Page) -> Page:
    await page.route("**/*", lambda route: route.abort())
    await page.route(
        BOSS_MATERIAL_URL, lambda route: route.fulfill(body=HTML, content_type="text/html")
    )
    await page.goto(BOSS_MATERIAL_URL)
    return page


def observer(page: Page) -> BossMaterialObserver:
    return BossMaterialObserver(page, lease_guard=guard, site_guard=guard)


@pytest.mark.asyncio
async def test_visible_metadata_read_has_no_page_mutation_or_private_data(
    material_page: Page,
) -> None:
    page = material_page
    # Fixture-only trap: a dangerous implementation would execute/inspect this;
    # the fixed read-only collector observes only rendered text/geometry.
    await page.evaluate(
        """() => {
            window.privateStore = new Proxy({}, {get() {throw Error('private store read')}});
            Element.prototype.click = () => {throw Error('script click')};
            window.fetch = () => {throw Error('private request')};
        }"""
    )
    before = await page.locator("body").inner_html()
    result = await observer(page).observe()
    assert result.state == "observed", result.reason
    assert result.materials[0].filename == "Synthetic.pdf"
    assert result.identity_basis == "rendered_metadata"
    assert await page.locator("body").inner_html() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "revision.hidden = true",
        "revision.style.opacity = '0'",
        "row.style.opacity = '0.5'",
        "revision.style.visibility = 'hidden'",
        "revision.style.position = 'absolute'; revision.style.top = '3000px'",
        "row.setAttribute('aria-hidden', 'true')",
        "revision.textContent = ''",
        "filename.textContent = 'Synthe….pdf'; filename.title = 'Synthetic.pdf'",
        "filename.style.display = 'inline-block'; filename.style.width = '30px'; "
        "filename.style.overflow = 'hidden'; filename.style.whiteSpace = 'nowrap'",
        "document.querySelector('#count').textContent = '文件(2/3)'",
        "document.querySelector('#count').textContent = '文件(0/3)'",
        "document.querySelector('#manager').after(document.querySelector('#manager').cloneNode(true))",
        "const overlay = document.createElement('div'); "
        "overlay.style.cssText = 'position:fixed;inset:0;background:white;z-index:99'; "
        "document.body.append(overlay)",
    ],
)
async def test_unreadable_or_ambiguous_material_is_unknown(
    material_page: Page, mutation: str
) -> None:
    await material_page.evaluate(
        "() => { const revision = document.querySelector('#revision'), "
        "row = document.querySelector('#row'), filename = document.querySelector('#filename'); "
        + mutation
        + " }"
    )
    result = await observer(material_page).observe()
    assert result.state == "unknown" and not result.materials


@pytest.mark.asyncio
async def test_material_revision_changes_reference_and_empty_requires_empty_panel(
    material_page: Page,
) -> None:
    first = await observer(material_page).observe()
    await material_page.locator("#revision").evaluate(
        "element => element.textContent = '2026.10.14 09:31'"
    )
    second = await observer(material_page).observe()
    assert first.materials[0].reference != second.materials[0].reference
    await material_page.evaluate(
        "() => {document.querySelector('#row').remove(); "
        "document.querySelector('#count').textContent = '文件(0/3)'}"
    )
    assert (await observer(material_page).observe()).state == "empty"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "notice, reason",
    [
        ("访问受限", "denied"),
        ("安全验证", "challenge"),
        ("操作过于频繁", "rate_limited"),
        ("账号异常", "abnormal"),
    ],
)
async def test_visible_risk_persists_and_blocks_subsequent_observation(
    material_page: Page, lease: LeaseHarness, notice: str, reason: RiskReason
) -> None:
    # Test-only synthetic HTML mutation; not a platform operation.
    await material_page.evaluate(
        "notice => {const warning = document.createElement('p'); "
        "warning.textContent = notice; document.body.prepend(warning)}",
        notice,
    )
    safety = PostgresSiteSafetyStore(lease.engine, BOSS_SCOPE)
    guarded = BossMaterialObserver(
        material_page,
        lease_guard=lease.guard,
        site_guard=lambda: safety.action_guard(lease.command.session_id, lease.command.sub),
    )
    with pytest.raises(SiteRiskDetected) as error:
        await guarded.observe()
    assert error.value.reason == reason
    async with lease.engine.connect() as connection:
        assert (
            await connection.scalar(
                text("SELECT reason FROM browser.site_safety WHERE user_id=:user AND site='boss'"),
                {"user": lease.command.sub},
            )
            == reason
        )
    # Even removing the warning cannot recover automatic observation.
    await material_page.set_content(HTML)
    original = material_page.evaluate
    spy = AsyncMock(wraps=original)
    material_page.evaluate = spy  # type: ignore[method-assign]
    try:
        with pytest.raises(SiteSafetyBlocked):
            await guarded.observe()
        spy.assert_not_awaited()
    finally:
        material_page.evaluate = original  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_hidden_risk_text_is_not_collected_as_visible_evidence(material_page: Page) -> None:
    await material_page.evaluate(
        "() => {const hidden = document.createElement('p'); hidden.hidden = true; "
        "hidden.textContent = '访问受限'; document.body.append(hidden)}"
    )
    assert (await observer(material_page).observe()).state == "observed"


@pytest.mark.asyncio
async def test_fading_visually_present_risk_notice_still_stops(material_page: Page) -> None:
    await material_page.evaluate(
        "() => {const warning = document.createElement('p'); warning.style.opacity = '0.5'; "
        "warning.setAttribute('aria-hidden', 'true'); warning.textContent = 'Access denied'; "
        "document.body.prepend(warning)}"
    )
    with pytest.raises(SiteRiskDetected):
        await observer(material_page).observe()
