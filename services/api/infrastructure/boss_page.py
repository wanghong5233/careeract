from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from services.api.application.ports.boss_page import BossPageObservation
from services.api.application.ports.browser_control import (
    BrowserControlConflict,
    BrowserControlContext,
    BrowserControlRejected,
    BrowserControlUncertain,
)
from services.api.infrastructure.browser_control import BrowserCommandSigner


class BossPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    session_id: UUID
    page: BossPageObservation


class BossPageClient:
    def __init__(self, client: httpx.AsyncClient, signer: BrowserCommandSigner) -> None:
        self.client = client
        self.signer = signer

    async def read_boss_page(self, context: BrowserControlContext) -> BossPageObservation:
        if context.owner_id != "boss-page-reader":
            raise BrowserControlRejected("Browser page read requires its dedicated scope")
        token = self.signer.sign(context, "snapshot")
        try:
            async with self.client.stream(
                "POST",
                f"/internal/v1/sessions/{context.session_id}/boss/page",
                headers={"Authorization": "Bearer " + token},
                follow_redirects=False,
                timeout=20,
            ) as response:
                if response.status_code in (401, 403):
                    raise BrowserControlRejected("Browser page read rejected")
                if response.status_code in (404, 409):
                    raise BrowserControlConflict("Browser page read requires reconciliation")
                if (
                    response.status_code != 200
                    or response.headers.get("content-type", "").split(";", 1)[0]
                    != "application/json"
                ):
                    raise BrowserControlUncertain("Browser page read result unconfirmed")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > 512 * 1024:
                        raise BrowserControlUncertain("Browser page read response exceeds limit")
                    content.extend(chunk)
        except httpx.TransportError:
            raise BrowserControlUncertain("Browser page read response unavailable") from None
        try:
            result = BossPageResponse.model_validate_json(bytes(content))
        except ValidationError:
            raise BrowserControlUncertain("Browser page read response invalid") from None
        urls = [result.page.url]
        urls.extend(job.url for job in result.page.jobs if job.url is not None)
        urls.extend(item.url for item in result.page.conversations if item.url is not None)
        try:
            invalid_url = any(
                urlsplit(url).scheme != "https"
                or urlsplit(url).hostname != "www.zhipin.com"
                or urlsplit(url).port not in (None, 443)
                or urlsplit(url).username is not None
                or urlsplit(url).password is not None
                for url in urls
            )
        except ValueError:
            raise BrowserControlUncertain("Browser page read source invalid") from None
        if (
            result.session_id != context.session_id
            or invalid_url
            or context.authorization_expires_at <= datetime.now(UTC)
        ):
            raise BrowserControlUncertain("Browser page read response does not match command")
        return result.page
