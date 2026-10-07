import json
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_CONTEXT_BYTES = 1024 * 1024


class BrowserContextRejected(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SiteScope:
    site: str
    origins: tuple[str, ...]
    cookie_domains: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.site or len(self.site) > 64 or not self.origins or not self.cookie_domains:
            raise ValueError("Browser site scope is invalid")
        for origin in self.origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or origin != "https://" + parsed.hostname
            ):
                raise ValueError("Browser site scope requires exact HTTPS origins")
        for domain in self.cookie_domains:
            if (
                not domain
                or domain != domain.lower().strip(".")
                or not any(
                    urlsplit(origin).hostname == domain
                    or str(urlsplit(origin).hostname).endswith("." + domain)
                    for origin in self.origins
                )
            ):
                raise ValueError("Browser cookie domain is outside the site scope")


class ContextCookie(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    name: str = Field(min_length=1, max_length=1024, repr=False)
    value: str = Field(max_length=16_384, repr=False)
    domain: str = Field(min_length=1, max_length=256)
    path: str = Field(default="/", min_length=1, max_length=2048)
    expires: float = Field(default=-1, allow_inf_nan=False)
    httpOnly: bool = False
    secure: bool = False
    sameSite: Literal["Strict", "Lax", "None"] | None = None
    partitionKey: dict[str, object] | None = Field(default=None, repr=False)


class StorageEntry(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    name: str = Field(max_length=16_384, repr=False)
    value: str = Field(max_length=MAX_CONTEXT_BYTES, repr=False)


class StorageOrigin(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    origin: str = Field(max_length=2048)
    localStorage: list[StorageEntry] = Field(max_length=4096, repr=False)


class PlaywrightState(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    cookies: list[ContextCookie] = Field(max_length=512, repr=False)
    origins: list[StorageOrigin] = Field(max_length=128, repr=False)


class BrowserContext(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    cookies: list[ContextCookie] = Field(default_factory=list, max_length=512, repr=False)
    localStorage: dict[str, dict[str, str]] = Field(default_factory=dict, repr=False)

    @classmethod
    def from_playwright(cls, payload: object, scope: SiteScope) -> "BrowserContext":
        try:
            state = PlaywrightState.model_validate(payload)
        except ValidationError:
            raise BrowserContextRejected("Browser storage snapshot is invalid") from None
        local_storage: dict[str, dict[str, str]] = {}
        seen: set[str] = set()
        for item in state.origins:
            if item.origin not in scope.origins:
                continue
            values = {entry.name: entry.value for entry in item.localStorage}
            if item.origin in seen or len(values) != len(item.localStorage):
                raise BrowserContextRejected("Browser storage snapshot is ambiguous")
            seen.add(item.origin)
            local_storage[item.origin] = values
        return cls.from_steel(
            {
                "cookies": [cookie.model_dump() for cookie in state.cookies],
                "localStorage": local_storage,
            },
            scope,
        )

    @classmethod
    def from_steel(cls, payload: object, scope: SiteScope) -> "BrowserContext":
        try:
            context = cls.model_validate(payload)
        except ValidationError:
            raise BrowserContextRejected("Browser context is invalid") from None
        cookies = [
            cookie
            for cookie in context.cookies
            if cookie.domain.lower().lstrip(".") in scope.cookie_domains
        ]
        if any(
            cookie.partitionKey is not None or not cookie.path.startswith("/") for cookie in cookies
        ):
            raise BrowserContextRejected("Browser context contains unsupported cookies")
        local_storage: dict[str, dict[str, str]] = {}
        for origin in scope.origins:
            hostname = str(urlsplit(origin).hostname)
            exact = context.localStorage.get(origin)
            domain = context.localStorage.get(hostname)
            if exact is not None and domain is not None and exact != domain:
                raise BrowserContextRejected("Browser storage origin is ambiguous")
            values = exact if exact is not None else domain
            if values:
                local_storage[origin] = values
        normalized = cls(cookies=cookies, localStorage=local_storage)
        if not cookies and not local_storage:
            raise BrowserContextRejected("Browser context has no scoped state")
        normalized.encode()
        return normalized

    def encode(self) -> bytes:
        payload = json.dumps(self.to_steel(), ensure_ascii=False, separators=(",", ":")).encode()
        if len(payload) > MAX_CONTEXT_BYTES:
            raise BrowserContextRejected("Browser context exceeds the storage limit")
        return payload

    def to_steel(self) -> dict[str, object]:
        return self.model_dump(exclude_none=True)
