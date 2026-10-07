from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from services.browser.sessions.context import BrowserContext, BrowserContextRejected, SiteScope
from services.browser.sessions.profiles import (
    BrowserProfile,
    BrowserProfileUnavailable,
    ProfileCipher,
)


def scope() -> SiteScope:
    return SiteScope("example", ("https://example.com",), ("example.com",))


def synthetic_context(value: str = "synthetic-private-state") -> BrowserContext:
    return BrowserContext.from_steel(
        {
            "cookies": [
                {
                    "name": "synthetic",
                    "value": value,
                    "domain": ".example.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax",
                }
            ],
            "localStorage": {"example.com": {"synthetic": value}},
        },
        scope(),
    )


def test_context_filters_third_party_state_and_uses_explicit_origins() -> None:
    payload = synthetic_context().to_steel()
    payload["localStorage"] = {
        "example.com": {"synthetic": "scoped"},
        "other.invalid": {"foreign": "private"},
    }
    payload["cookies"] = [{"name": "foreign", "value": "private", "domain": "other.invalid"}]
    context = BrowserContext.from_steel(payload, scope())
    assert context.localStorage == {"https://example.com": {"synthetic": "scoped"}}
    assert not context.cookies
    assert "private" not in repr(context)
    assert "foreign" not in context.encode().decode()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"cookies": "private-malformed"},
        {"localStorage": {"example.com": {"bad": 4}}},
        {"cookies": [{"name": "a", "value": "b", "domain": "foreign.invalid"}]},
        {"localStorage": {"http://example.com": {"private": "unsupported"}}},
        {
            "localStorage": {
                "example.com": {"value": "first"},
                "https://example.com": {"value": "different"},
            }
        },
        {
            "cookies": [
                {
                    "name": "a",
                    "value": "private",
                    "domain": "example.com",
                    "partitionKey": {"topLevelSite": "https://example.com"},
                }
            ]
        },
        {"localStorage": {"example.com": {"private": "x" * (1024 * 1024)}}},
    ],
)
def test_unverified_or_malformed_context_is_rejected_without_input_echo(payload: object) -> None:
    with pytest.raises(BrowserContextRejected) as rejected:
        BrowserContext.from_steel(payload, scope())
    assert "private" not in str(rejected.value)


@pytest.mark.parametrize(
    "origin", ["http://example.com", "https://example.com/", "https://user@example.com"]
)
def test_scope_requires_canonical_https_origins(origin: str) -> None:
    with pytest.raises(ValueError):
        SiteScope("example", (origin,), ("example.com",))


def test_live_snapshot_keeps_exact_origin_and_filters_other_storage() -> None:
    payload = {
        "cookies": [],
        "origins": [
            {"origin": "https://example.com", "localStorage": [{"name": "state", "value": "live"}]},
            {"origin": "http://example.com", "localStorage": [{"name": "state", "value": "wrong"}]},
            {
                "origin": "https://other.invalid",
                "localStorage": [{"name": "state", "value": "foreign"}],
            },
        ],
        "localStorage": {"https://example.com": {"state": "stale-disk"}},
    }
    context = BrowserContext.from_playwright(payload, scope())
    assert context.localStorage == {"https://example.com": {"state": "live"}}
    assert "stale-disk" not in context.encode().decode()


@pytest.mark.parametrize("duplicate_origin", [True, False])
def test_live_snapshot_rejects_duplicate_origins_or_keys(duplicate_origin: bool) -> None:
    entry = {"name": "private", "value": "first"}
    origins = [{"origin": "https://example.com", "localStorage": [entry]}]
    if duplicate_origin:
        origins.append({"origin": "https://example.com", "localStorage": []})
    else:
        origins[0]["localStorage"] = [entry, {"name": "private", "value": "different"}]
    with pytest.raises(BrowserContextRejected) as rejected:
        BrowserContext.from_playwright({"cookies": [], "origins": origins}, scope())
    assert "private" not in str(rejected.value)


def test_aead_binds_user_site_version_expiry_and_scope() -> None:
    cipher = ProfileCipher(AESGCM.generate_key(bit_length=256))
    profile = BrowserProfile(
        uuid4(), "synthetic-user", "example", uuid4(), datetime.now(UTC) + timedelta(days=1)
    )
    context = synthetic_context()
    encrypted = cipher.encrypt(profile, scope(), context)
    assert b"synthetic-private-state" not in encrypted
    assert encrypted != cipher.encrypt(profile, scope(), context)
    assert cipher.decrypt(profile, scope(), encrypted) == context
    for changed in (
        replace(profile, id=uuid4()),
        replace(profile, user_id="another-user"),
        replace(profile, site="another-site"),
        replace(profile, version=uuid4()),
        replace(profile, expires_at=profile.expires_at + timedelta(days=1)),
    ):
        with pytest.raises(BrowserProfileUnavailable):
            cipher.decrypt(changed, scope(), encrypted)
    with pytest.raises(BrowserProfileUnavailable):
        cipher.decrypt(profile, scope(), encrypted[:-1] + bytes([encrypted[-1] ^ 1]))
    with pytest.raises(BrowserProfileUnavailable):
        ProfileCipher(AESGCM.generate_key(bit_length=256)).decrypt(profile, scope(), encrypted)
    with pytest.raises(BrowserProfileUnavailable):
        cipher.decrypt(
            profile,
            SiteScope("example", ("https://www.example.com",), ("example.com",)),
            encrypted,
        )
    assert "synthetic-private-state" not in repr(context)
    assert "synthetic-private-state" not in repr(context.cookies[0])


def test_profile_key_requires_a_dedicated_raw_key_file(tmp_path: Path) -> None:
    with pytest.raises(BrowserProfileUnavailable):
        ProfileCipher.from_file(tmp_path / "missing")
    key_file = tmp_path / "synthetic-key"
    key_file.write_bytes(b"invalid")
    with pytest.raises(BrowserProfileUnavailable):
        ProfileCipher.from_file(key_file)
    key_file.write_bytes(AESGCM.generate_key(bit_length=256))
    assert isinstance(ProfileCipher.from_file(key_file), ProfileCipher)
