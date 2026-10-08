import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.browser.sessions.context import BrowserContext, BrowserContextRejected, SiteScope


class BrowserProfileConflict(Exception):
    pass


class BrowserProfileUnavailable(Exception):
    pass


@dataclass(frozen=True, slots=True)
class BrowserProfile:
    id: UUID
    user_id: str
    site: str
    version: UUID
    expires_at: datetime
    revoked: bool = False


class ProfileCipher:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("Browser profile encryption requires a 32-byte key")
        self._cipher = AESGCM(key)

    @classmethod
    def from_file(cls, path: Path) -> "ProfileCipher":
        try:
            return cls(path.read_bytes())
        except (OSError, ValueError):
            raise BrowserProfileUnavailable(
                "Browser profile key is unavailable or invalid"
            ) from None

    @staticmethod
    def _binding(profile: BrowserProfile, scope: SiteScope) -> bytes:
        return json.dumps(
            [
                "careeract-browser-profile-v1",
                str(profile.id),
                profile.user_id,
                profile.site,
                str(profile.version),
                profile.expires_at.isoformat(),
                scope.origins,
                scope.cookie_domains,
            ],
            separators=(",", ":"),
        ).encode()

    def encrypt(self, profile: BrowserProfile, scope: SiteScope, context: BrowserContext) -> bytes:
        nonce = os.urandom(12)
        normalized = BrowserContext.from_steel(context.to_steel(), scope)
        return nonce + self._cipher.encrypt(
            nonce, normalized.encode(), self._binding(profile, scope)
        )

    def decrypt(
        self, profile: BrowserProfile, scope: SiteScope, encrypted: bytes
    ) -> BrowserContext:
        try:
            decoded = self._cipher.decrypt(
                encrypted[:12], encrypted[12:], self._binding(profile, scope)
            )
            return BrowserContext.from_steel(json.loads(decoded), scope)
        except (InvalidTag, ValueError, BrowserContextRejected):
            raise BrowserProfileUnavailable("Browser profile cannot be decrypted") from None


def profile_from_row(row: RowMapping) -> BrowserProfile:
    return BrowserProfile(
        id=row["id"],
        user_id=row["user_id"],
        site=row["site"],
        version=row["version"],
        expires_at=row["expires_at"],
        revoked=row["revoked"],
    )


class PostgresBrowserProfileStore:
    def __init__(
        self,
        engine: AsyncEngine,
        cipher: ProfileCipher,
        scope: SiteScope,
        *,
        retention: timedelta = timedelta(days=30),
    ) -> None:
        if not timedelta(0) < retention <= timedelta(days=30):
            raise ValueError("Browser profile retention must be within 30 days")
        self.engine = engine
        self.cipher = cipher
        self.scope = scope
        self.retention = retention

    async def create(self, user_id: str, context: BrowserContext) -> BrowserProfile:
        try:
            async with self.engine.begin() as connection:
                now = await connection.scalar(text("SELECT clock_timestamp()"))
                profile = BrowserProfile(
                    uuid4(), user_id, self.scope.site, uuid4(), now + self.retention
                )
                encrypted = self.cipher.encrypt(profile, self.scope, context)
                created = await connection.scalar(
                    text(
                        "INSERT INTO browser.profiles "
                        "(id,user_id,site,version,expires_at,ciphertext) "
                        "VALUES (:id,:user_id,:site,:version,:expires_at,:ciphertext) "
                        "ON CONFLICT (user_id,site) WHERE revoked=false DO NOTHING RETURNING id"
                    ),
                    {
                        "id": profile.id,
                        "user_id": user_id,
                        "site": profile.site,
                        "version": profile.version,
                        "expires_at": profile.expires_at,
                        "ciphertext": encrypted,
                    },
                )
                if created is None:
                    raise BrowserProfileConflict("A browser profile already exists for this site")
                return profile
        except (DBAPIError, PoolTimeoutError):
            raise BrowserProfileUnavailable("Browser profile storage is unavailable") from None

    async def read(
        self, user_id: str, profile_id: UUID
    ) -> tuple[BrowserProfile, BrowserContext] | None:
        try:
            async with self.engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM browser.profiles WHERE id=:id AND user_id=:user_id "
                                "AND site=:site AND revoked=false AND expires_at>clock_timestamp()"
                            ),
                            {"id": profile_id, "user_id": user_id, "site": self.scope.site},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return None
                profile = profile_from_row(row)
                return profile, self.cipher.decrypt(profile, self.scope, row["ciphertext"])
        except (DBAPIError, PoolTimeoutError):
            raise BrowserProfileUnavailable("Browser profile storage is unavailable") from None

    async def current(self, user_id: str) -> tuple[BrowserProfile, BrowserContext] | None:
        try:
            async with self.engine.connect() as connection:
                profile_id = await connection.scalar(
                    text(
                        "SELECT id FROM browser.profiles WHERE user_id=:user_id AND site=:site "
                        "AND revoked=false AND expires_at>clock_timestamp()"
                    ),
                    {"user_id": user_id, "site": self.scope.site},
                )
            return None if profile_id is None else await self.read(user_id, profile_id)
        except (DBAPIError, PoolTimeoutError):
            raise BrowserProfileUnavailable("Browser profile storage is unavailable") from None

    async def save(
        self, user_id: str, profile_id: UUID, context: BrowserContext, *, expected_version: UUID
    ) -> BrowserProfile:
        return await self._change(user_id, profile_id, expected_version, context)

    async def revoke(
        self, user_id: str, profile_id: UUID, *, expected_version: UUID
    ) -> BrowserProfile:
        return await self._change(user_id, profile_id, expected_version, None)

    async def _change(
        self, user_id: str, profile_id: UUID, expected_version: UUID, context: BrowserContext | None
    ) -> BrowserProfile:
        try:
            async with self.engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM browser.profiles WHERE id=:id AND user_id=:user_id "
                                "AND site=:site FOR UPDATE"
                            ),
                            {"id": profile_id, "user_id": user_id, "site": self.scope.site},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise BrowserProfileConflict("Browser profile is unavailable")
                if row["revoked"] and context is None:
                    return profile_from_row(row)
                now = await connection.scalar(text("SELECT clock_timestamp()"))
                if (
                    row["version"] != expected_version
                    or row["revoked"]
                    or (context is not None and row["expires_at"] <= now)
                ):
                    raise BrowserProfileConflict("Browser profile changed or requires a new login")
                profile = BrowserProfile(
                    profile_id,
                    user_id,
                    self.scope.site,
                    uuid4(),
                    row["expires_at"],
                    context is None,
                )
                encrypted = self.cipher.encrypt(profile, self.scope, context) if context else None
                await connection.execute(
                    text(
                        "UPDATE browser.profiles SET version=:version,ciphertext=:ciphertext,"
                        "revoked=:revoked,updated_at=clock_timestamp() WHERE id=:id"
                    ),
                    {
                        "id": profile_id,
                        "version": profile.version,
                        "ciphertext": encrypted,
                        "revoked": profile.revoked,
                    },
                )
                return profile
        except (DBAPIError, PoolTimeoutError):
            raise BrowserProfileUnavailable("Browser profile storage is unavailable") from None
