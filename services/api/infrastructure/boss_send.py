from dataclasses import replace
from hashlib import sha256

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from services.api.application.ports.browser_control import (
    BrowserControlConflict,
    BrowserControlRejected,
    BrowserControlUncertain,
)
from services.api.application.ports.communication_send import SendClaim
from services.api.domain.communication_send import SendEvidence
from services.api.infrastructure.browser_control import BrowserCommandSigner


class SendResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str
    message_id: str | None = None


class BossMessageSender:
    def __init__(self, client: httpx.AsyncClient, signer: BrowserCommandSigner) -> None:
        self.client, self.signer = client, signer

    async def send_message(self, claim: SendClaim) -> SendEvidence:
        context = replace(
            claim.context,
            message_id=claim.message_id,
            text_digest=sha256(claim.text.encode()).hexdigest(),
            source_digest=sha256(claim.source_text.encode()).hexdigest(),
        )
        token = self.signer.sign(context, "send_message")
        try:
            response = await self.client.post(
                f"/internal/v1/sessions/{context.session_id}/boss/send-message",
                headers={"Authorization": "Bearer " + token},
                json={"text": claim.text, "source_text": claim.source_text},
                follow_redirects=False,
                timeout=40,
            )
        except httpx.TransportError:
            raise BrowserControlUncertain("Send response lost; do not retry") from None
        if response.status_code in {401, 403}:
            raise BrowserControlRejected("Send authorization rejected")
        if response.status_code in {404, 409}:
            raise BrowserControlConflict("Send control unavailable")
        if response.status_code != 200:
            raise BrowserControlUncertain("Send result unconfirmed")
        try:
            result = SendResponse.model_validate_json(response.content)
            if result.state not in {"completed", "failed", "unknown"} or (
                result.state == "completed" and not result.message_id
            ):
                raise ValueError("Invalid evidence")
            return SendEvidence(result.state, result.message_id)
        except (ValidationError, ValueError):
            raise BrowserControlUncertain("Send evidence unavailable") from None
