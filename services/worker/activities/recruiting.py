from uuid import UUID

import httpx
from temporalio import activity
from temporalio.exceptions import ApplicationError


class RecruitingActivities:
    """Only opaque references cross Temporal and the authenticated service boundary."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def execute(self, action: str, reference: str) -> None:
        reference = str(UUID(reference))
        try:
            response = await self.client.post(f"/internal/recruiting/{action}/{reference}")
        except httpx.HTTPError:
            # Never put response bodies, credentials or HR content into History.
            raise ApplicationError(
                "Recruiting executor unavailable", type="ExecutorUnavailable"
            ) from None
        if response.status_code != 204:
            raise ApplicationError(
                "Recruiting executor rejected operation",
                type="ExecutorRejected",
                non_retryable=response.status_code < 500,
            )

    @activity.defn(name="generate_recruiting_reply")
    async def generate(self, reference: str) -> None:
        await self.execute("generate", reference)

    @activity.defn(name="send_recruiting_reply")
    async def send_reply(self, reference: str) -> None:
        await self.execute("send", reference)

    @activity.defn(name="reconcile_recruiting_send")
    async def reconcile_send(self, reference: str) -> None:
        await self.execute("cleanup-send", reference)

    @activity.defn(name="read_recruiting_conversation")
    async def read(self, reference: str) -> None:
        await self.execute("read", reference)

    @activity.defn(name="stop_recruiting_read")
    async def stop_read(self, reference: str) -> None:
        await self.execute("stop-read", reference)

    @activity.defn(name="step_recruiting_automation")
    async def automation_step(self, reference: str) -> int:
        reference = str(UUID(reference))
        try:
            response = await self.client.post(f"/internal/recruiting/automation-step/{reference}")
        except httpx.HTTPError:
            raise ApplicationError(
                "Delegation step unconfirmed", type="ExecutorUnavailable"
            ) from None
        if response.status_code != 204:
            raise ApplicationError("Delegation step rejected", type="ExecutorRejected")
        try:
            delay = int(response.headers["X-Next-Step-Seconds"])
        except (KeyError, ValueError):
            raise ApplicationError("Invalid delegation result", type="ExecutorRejected") from None
        if not 0 <= delay <= 3600:
            raise ApplicationError("Invalid delegation delay", type="ExecutorRejected")
        return delay

    @activity.defn(name="halt_recruiting_automation")
    async def halt_automation(self, reference: str) -> None:
        await self.execute("automation-halt", reference)
