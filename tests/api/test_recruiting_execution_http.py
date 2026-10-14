from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from temporalio.exceptions import ApplicationError

from services.api.infrastructure.authentication import JwtAuthenticationMiddleware
from services.api.routes.recruiting_execution import RecruitingExecutor, router
from services.worker.activities.recruiting import RecruitingActivities

TEST_KEY = "synthetic-worker-credential-for-tests"


def execution_app(executor: RecruitingExecutor, key: str | None = TEST_KEY) -> FastAPI:
    app = FastAPI()
    app.state.recruiting_execution = executor
    app.include_router(router)
    app.add_middleware(
        JwtAuthenticationMiddleware,
        jwks_url="http://unused.test/jwks",
        issuer="test",
        audience="test",
        algorithms=["EdDSA"],
        jwks_timeout_seconds=1,
        public_paths=[],
        protected_path_prefixes=["/api/"],
        worker_api_key=key,
    )
    return app


def http_activities(executor: RecruitingExecutor) -> RecruitingActivities:
    return RecruitingActivities(
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=execution_app(executor)),
            base_url="http://api.test",
            headers={"Authorization": f"Bearer {TEST_KEY}"},
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [TEST_KEY, None])
@pytest.mark.parametrize("credential", [None, "product-jwt", "wrong-service-key"])
async def test_internal_executor_rejects_missing_wrong_and_product_credentials(
    key: str | None, credential: str | None
) -> None:
    executor = AsyncMock()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=execution_app(executor, key)), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/internal/recruiting/send/{uuid4()}",
            headers={"Authorization": f"Bearer {credential}"} if credential else {},
        )
    assert response.status_code == 401
    executor.send_reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_automation_activity_returns_bounded_delay_without_private_content() -> None:
    executor = AsyncMock()
    executor.automation_step.return_value = 300
    activities = http_activities(executor)
    reference = str(uuid4())
    try:
        assert await activities.automation_step(reference) == 300
        executor.automation_step.assert_awaited_once_with(reference)
        executor.automation_step.return_value = 3601
        with pytest.raises(ApplicationError, match="Invalid delegation delay"):
            await activities.automation_step(reference)
        await activities.halt_automation(reference)
        executor.halt_automation.assert_awaited_once_with(reference)
    finally:
        await activities.client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["generate", "read", "stop-read", "send", "cleanup-send"])
async def test_worker_http_executes_only_the_recorded_reference(action: str) -> None:
    executor = AsyncMock()
    activities = http_activities(executor)
    reference = str(uuid4())
    async with activities.client:
        await activities.execute(action, reference)
    method = {"stop-read": "stop_read", "send": "send_reply", "cleanup-send": "reconcile_send"}.get(
        action, action
    )
    getattr(executor, method).assert_awaited_once_with(reference)


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", ["body", "query", "unknown-action"])
async def test_internal_executor_cannot_supply_actor_content_or_permissions(extra: str) -> None:
    executor = AsyncMock()
    activities = http_activities(executor)
    action = "arbitrary" if extra == "unknown-action" else "send"
    async with activities.client as client:
        response = await client.post(
            f"/internal/recruiting/{action}/{uuid4()}",
            json={"user_id": "other", "authorize_send": True} if extra == "body" else None,
            params={"user_id": "other"} if extra == "query" else None,
        )
    assert response.status_code in {400, 422}
    executor.send_reply.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["response", "timeout"])
async def test_worker_loss_is_not_retried_and_never_discloses_body_to_history(failure: str) -> None:
    calls = []

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private-message-and-credential", request=request)
        return httpx.Response(503, text="private-message-and-credential")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(transport), base_url="http://test"
    ) as client:
        with pytest.raises(ApplicationError) as raised:
            await RecruitingActivities(client).send_reply(str(uuid4()))
    assert len(calls) == 1
    assert "private-message-and-credential" not in str(raised.value)


def test_internal_executor_is_not_in_public_openapi() -> None:
    assert not execution_app(AsyncMock()).openapi()["paths"]
