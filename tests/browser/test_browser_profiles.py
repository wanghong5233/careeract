import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from playwright.async_api import async_playwright
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from scripts.smoke_steel_profile import websocket_url
from services.browser.sessions.context import BrowserContext, BrowserContextRejected, SiteScope
from services.browser.sessions.profiles import (
    BrowserProfileConflict,
    BrowserProfileUnavailable,
    PostgresBrowserProfileStore,
    ProfileCipher,
)
from services.browser.sessions.steel import SteelSessionManager
from tests.browser.test_browser_context import scope, synthetic_context
from tests.browser.test_postgres_leases import database_url as database_url

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL integration",
)


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url, hide_parameters=True)
    try:
        yield engine
    finally:
        await engine.dispose()


async def add_user(engine: AsyncEngine) -> str:
    user_id = "synthetic-profile-" + uuid4().hex
    async with engine.begin() as connection:
        await connection.execute(
            text(
                'INSERT INTO auth."user" (id,name,email,"emailVerified") '
                "VALUES (:id,'Synthetic',:email,false)"
            ),
            {"id": user_id, "email": user_id + "@example.invalid"},
        )
    return user_id


@pytest.mark.asyncio
async def test_encrypted_profile_survives_reconstruction_and_preserves_user_scope(
    engine: AsyncEngine,
) -> None:
    key = AESGCM.generate_key(bit_length=256)
    store = PostgresBrowserProfileStore(engine, ProfileCipher(key), scope())
    user_id, other_id = await add_user(engine), await add_user(engine)
    context = synthetic_context()
    profile = await store.create(user_id, context)
    async with engine.connect() as connection:
        ciphertext = await connection.scalar(
            text("SELECT ciphertext FROM browser.profiles WHERE id=:id"), {"id": profile.id}
        )
        assert isinstance(ciphertext, bytes)
        assert b"synthetic-private-state" not in ciphertext
    await engine.dispose()
    restarted = PostgresBrowserProfileStore(engine, ProfileCipher(key), scope())
    assert await restarted.read(user_id, profile.id) == (profile, context)
    assert await restarted.read(other_id, profile.id) is None
    other_site = PostgresBrowserProfileStore(
        engine,
        ProfileCipher(key),
        SiteScope("other", ("https://example.com",), ("example.com",)),
    )
    assert await other_site.read(user_id, profile.id) is None
    with pytest.raises(BrowserProfileConflict):
        await restarted.save(other_id, profile.id, context, expected_version=profile.version)
    with pytest.raises(BrowserProfileConflict):
        await restarted.revoke(other_id, profile.id, expected_version=profile.version)
    assert await restarted.read(user_id, profile.id) == (profile, context)
    wrong_key_store = PostgresBrowserProfileStore(
        engine, ProfileCipher(AESGCM.generate_key(bit_length=256)), scope()
    )
    with pytest.raises(BrowserProfileUnavailable):
        await wrong_key_store.read(user_id, profile.id)


@pytest.mark.asyncio
async def test_two_connections_compete_for_creation_and_conditional_updates(
    engine: AsyncEngine,
) -> None:
    key = AESGCM.generate_key(bit_length=256)
    user_id = await add_user(engine)
    context = synthetic_context()
    other_engine = create_async_engine(str(engine.url), hide_parameters=True)
    stores = [
        PostgresBrowserProfileStore(item, ProfileCipher(key), scope())
        for item in (engine, other_engine)
    ]
    try:
        creation = await asyncio.gather(
            *(store.create(user_id, context) for store in stores), return_exceptions=True
        )
        assert sum(isinstance(item, BrowserProfileConflict) for item in creation) == 1
        current = next(item for item in creation if not isinstance(item, BaseException))
        saved = await asyncio.gather(
            *(
                store.save(user_id, current.id, context, expected_version=current.version)
                for store in stores
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(item, BrowserProfileConflict) for item in saved) == 1
        updated = next(item for item in saved if not isinstance(item, BaseException))
        assert updated.version != current.version
        assert updated.expires_at == current.expires_at
        assert await stores[0].read(user_id, updated.id) == (updated, context)
    finally:
        await other_engine.dispose()


@pytest.mark.asyncio
async def test_revocation_clears_ciphertext_and_blocks_late_saves(engine: AsyncEngine) -> None:
    store = PostgresBrowserProfileStore(
        engine, ProfileCipher(AESGCM.generate_key(bit_length=256)), scope()
    )
    user_id = await add_user(engine)
    context = synthetic_context()
    profile = await store.create(user_id, context)
    revoked = await store.revoke(user_id, profile.id, expected_version=profile.version)
    assert revoked.revoked
    assert await store.read(user_id, profile.id) is None
    assert await store.revoke(user_id, profile.id, expected_version=profile.version) == revoked
    async with engine.connect() as connection:
        assert await connection.scalar(
            text("SELECT ciphertext IS NULL FROM browser.profiles WHERE id=:id"), {"id": profile.id}
        )
    replacement = await store.create(user_id, synthetic_context("fresh-login"))
    for version in (profile.version, revoked.version):
        with pytest.raises(BrowserProfileConflict):
            await store.save(user_id, profile.id, context, expected_version=version)
    assert (await store.read(user_id, replacement.id)) == (
        replacement,
        synthetic_context("fresh-login"),
    )


@pytest.mark.asyncio
async def test_save_racing_revoke_cannot_resurrect_profile(engine: AsyncEngine) -> None:
    store = PostgresBrowserProfileStore(
        engine, ProfileCipher(AESGCM.generate_key(bit_length=256)), scope()
    )
    user_id = await add_user(engine)
    context = synthetic_context()
    profile = await store.create(user_id, context)
    results = await asyncio.gather(
        store.save(user_id, profile.id, context, expected_version=profile.version),
        store.revoke(user_id, profile.id, expected_version=profile.version),
        return_exceptions=True,
    )
    assert sum(isinstance(item, BrowserProfileConflict) for item in results) == 1
    winner = next(item for item in results if not isinstance(item, BaseException))
    if not winner.revoked:
        await store.revoke(user_id, profile.id, expected_version=winner.version)
    assert await store.read(user_id, profile.id) is None
    with pytest.raises(BrowserProfileConflict):
        await store.save(user_id, profile.id, context, expected_version=profile.version)


@pytest.mark.asyncio
async def test_expiry_requires_explicit_new_login_and_allows_cleanup(engine: AsyncEngine) -> None:
    store = PostgresBrowserProfileStore(
        engine,
        ProfileCipher(AESGCM.generate_key(bit_length=256)),
        scope(),
        retention=timedelta(milliseconds=1),
    )
    user_id = await add_user(engine)
    context = synthetic_context()
    profile = await store.create(user_id, context)
    await asyncio.sleep(0.01)
    assert await store.read(user_id, profile.id) is None
    with pytest.raises(BrowserProfileConflict):
        await store.save(user_id, profile.id, context, expected_version=profile.version)
    with pytest.raises(BrowserProfileConflict):
        await store.create(user_id, context)
    assert (await store.revoke(user_id, profile.id, expected_version=profile.version)).revoked


@pytest.mark.asyncio
async def test_rejected_snapshot_cannot_overwrite_existing_profile(engine: AsyncEngine) -> None:
    store = PostgresBrowserProfileStore(
        engine, ProfileCipher(AESGCM.generate_key(bit_length=256)), scope()
    )
    user_id = await add_user(engine)
    original = synthetic_context()
    profile = await store.create(user_id, original)
    with pytest.raises(BrowserContextRejected):
        await store.save(user_id, profile.id, BrowserContext(), expected_version=profile.version)
    assert await store.read(user_id, profile.id) == (profile, original)


@pytest.mark.asyncio
async def test_ciphertext_swap_and_metadata_tamper_fail_closed(engine: AsyncEngine) -> None:
    store = PostgresBrowserProfileStore(
        engine, ProfileCipher(AESGCM.generate_key(bit_length=256)), scope()
    )
    first_id, second_id = await add_user(engine), await add_user(engine)
    first = await store.create(first_id, synthetic_context("first-state"))
    second = await store.create(second_id, synthetic_context("second-state"))
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE browser.profiles SET ciphertext="
                "(SELECT ciphertext FROM browser.profiles WHERE id=:source) WHERE id=:target"
            ),
            {"source": first.id, "target": second.id},
        )
    with pytest.raises(BrowserProfileUnavailable):
        await store.read(second_id, second.id)
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE browser.profiles SET expires_at=:expiry WHERE id=:id"),
            {
                "expiry": replace(
                    first, expires_at=first.expires_at + timedelta(days=1)
                ).expires_at,
                "id": first.id,
            },
        )
    with pytest.raises(BrowserProfileUnavailable):
        await store.read(first_id, first.id)


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_STEEL_PROFILE_TEST") != "1",
    reason="Opt-in real Steel encrypted context restore",
)
async def test_real_steel_restores_encrypted_profile_and_fresh_session_stays_clean(
    engine: AsyncEngine,
) -> None:
    key = AESGCM.generate_key(bit_length=256)
    store = PostgresBrowserProfileStore(engine, ProfileCipher(key), scope())
    user_id = await add_user(engine)
    marker = uuid4().hex
    name = "careeract-encrypted-canary"
    profile = None
    async with (
        httpx.AsyncClient(base_url="http://127.0.0.1:3001", timeout=40) as client,
        async_playwright() as playwright,
    ):
        manager = SteelSessionManager(client, engine)
        for stage in ("seed", "restore", "clean"):
            context = None
            if stage == "restore":
                assert profile is not None
                await engine.dispose()
                store = PostgresBrowserProfileStore(engine, ProfileCipher(key), scope())
                restored = await store.read(user_id, profile.id)
                assert restored is not None
                _, context = restored
                manager = SteelSessionManager(client, engine)
            session_id = uuid4()
            await manager.create(session_id, context=context)
            try:
                version = await client.get("http://127.0.0.1:9223/json/version")
                version.raise_for_status()
                browser = await playwright.chromium.connect_over_cdp(
                    websocket_url("http://127.0.0.1:9223", version.json()["webSocketDebuggerUrl"]),
                    headers={"Host": "localhost"},
                )
                try:
                    browser_context = browser.contexts[0]
                    page = await browser_context.new_page()
                    await page.goto(
                        "https://example.com", wait_until="domcontentloaded", timeout=30_000
                    )
                    if stage == "seed":
                        await browser_context.add_cookies(
                            [
                                {
                                    "name": name,
                                    "value": marker,
                                    "url": "https://example.com",
                                    "httpOnly": True,
                                    "secure": True,
                                    "sameSite": "Lax",
                                }
                            ]
                        )
                        await page.evaluate(
                            "item=>localStorage.setItem(item.name,item.value)",
                            {"name": name, "value": marker},
                        )
                        exported = await manager.export_context(
                            session_id, scope(), browser_context=browser_context
                        )
                        profile = await store.create(user_id, exported)
                        async with engine.connect() as connection:
                            ciphertext = await connection.scalar(
                                text("SELECT ciphertext FROM browser.profiles WHERE id=:id"),
                                {"id": profile.id},
                            )
                            assert marker.encode() not in ciphertext
                    else:
                        if stage == "restore":
                            await page.wait_for_function(
                                "item=>localStorage.getItem(item.name)===item.value",
                                arg={"name": name, "value": marker},
                                timeout=5_000,
                            )
                        stored = await page.evaluate("name=>localStorage.getItem(name)", name)
                        cookies = [
                            item
                            for item in await browser_context.cookies("https://example.com")
                            if item["name"] == name
                        ]
                        expected = marker if stage == "restore" else None
                        assert stored == expected
                        assert (cookies[0]["value"] if cookies else None) == expected
                        if cookies:
                            assert cookies[0]["httpOnly"] and cookies[0]["secure"]
                finally:
                    await browser.close()
            finally:
                await manager.release(session_id)
        assert profile is not None
        await store.revoke(user_id, profile.id, expected_version=profile.version)
        assert await store.read(user_id, profile.id) is None
