import asyncio
import os
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import text
from temporalio.common import RetryPolicy

from services.api.application.read_execution import ReadExecutionService
from services.api.domain.execution import ExecutionUnavailable
from services.api.infrastructure.read_dispatch import TemporalReadDispatcher
from services.api.infrastructure.read_execution import PostgresReadExecutionRepository
from tests.api.test_execution_semantics import Scenario
from tests.api.test_execution_semantics import scenario as scenario
from tests.api.test_recruiting_execution_http import http_activities
from tests.browser.test_postgres_leases import database_url as database_url

integration = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_POSTGRES_TESTS") != "1", reason="Opt-in isolated PostgreSQL"
)


@integration
@pytest.mark.asyncio
async def test_dispatch_restore_does_not_replay_browser_or_extend_authorization(
    scenario: Scenario,
) -> None:
    async with scenario.engine.begin() as db:
        version = await db.scalar(
            text(
                "UPDATE career.boss_connections SET status='connected', "
                "browser_session_id=:session "
                "WHERE id=:id RETURNING version"
            ),
            {"id": scenario.connection_id, "session": uuid4()},
        )
    dispatcher = AsyncMock()
    service = ReadExecutionService(PostgresReadExecutionRepository(scenario.engine), dispatcher)
    accepted = await service.accept_boss(
        scenario.actor,
        connection_id=scenario.connection_id,
        expected_version=version,
        request_key=uuid4(),
    )
    dispatcher.dispatch.side_effect = ExecutionUnavailable("saved, dispatch unconfirmed")
    with pytest.raises(ExecutionUnavailable):
        await service.dispatch_boss(scenario.actor, scenario.connection_id, accepted.task.id)
    assert await service.read(scenario.actor, accepted.task.id) == accepted
    dispatcher.dispatch.side_effect = None
    restored = await service.dispatch_boss(scenario.actor, scenario.connection_id, accepted.task.id)
    assert restored == accepted
    cancelled = await service.cancel(scenario.actor, accepted.task.id)
    assert (
        await service.dispatch_boss(scenario.actor, scenario.connection_id, accepted.task.id)
        == cancelled
    )
    assert dispatcher.dispatch.await_count == 2


@pytest.mark.asyncio
async def test_read_workflow_failure_cleans_up_without_browser_redelivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from temporalio.exceptions import ActivityError

    from services.worker.workflows.recruiting import RecruitingReadWorkflow

    calls = []

    async def execute(name: str, ref: str, **options: object) -> None:
        calls.append((name, ref, options))
        if name == "read_recruiting_conversation":
            raise ActivityError(
                "interrupted",
                scheduled_event_id=1,
                started_event_id=2,
                identity="test",
                activity_type=name,
                activity_id="1",
                retry_state=None,
            )

    monkeypatch.setattr("services.worker.workflows.recruiting.workflow.execute_activity", execute)
    with pytest.raises(ActivityError):
        await RecruitingReadWorkflow().run(str(uuid4()))
    assert [call[0] for call in calls] == ["read_recruiting_conversation", "stop_recruiting_read"]
    assert cast(RetryPolicy, calls[0][2]["retry_policy"]).maximum_attempts == 1


@pytest.mark.asyncio
async def test_automation_timer_and_failed_stage_do_not_repeat_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from temporalio.exceptions import ActivityError

    from services.worker.workflows.recruiting import RecruitingAutomationWorkflow

    calls: list[tuple[str, str, dict[str, object]]] = []
    delays = iter([300, 1])

    async def execute(name: str, ref: str, **options: object) -> int:
        calls.append((name, ref, options))
        if name == "halt_recruiting_automation":
            return 0
        try:
            return next(delays)
        except StopIteration:
            raise ActivityError(
                "interrupted",
                scheduled_event_id=1,
                started_event_id=2,
                identity="test",
                activity_type=name,
                activity_id="1",
                retry_state=None,
            ) from None

    timer = AsyncMock()
    monkeypatch.setattr("services.worker.workflows.recruiting.workflow.execute_activity", execute)
    monkeypatch.setattr("services.worker.workflows.recruiting.workflow.sleep", timer)
    reference = str(uuid4())
    with pytest.raises(ActivityError):
        await RecruitingAutomationWorkflow().run(reference)
    assert [c[0] for c in calls] == ["step_recruiting_automation"] * 3 + [
        "halt_recruiting_automation"
    ]
    assert all(c[1] == reference for c in calls)
    assert all(cast(RetryPolicy, c[2]["retry_policy"]).maximum_attempts == 1 for c in calls[:-1])
    assert timer.await_count == 2


@pytest.mark.skipif(
    os.environ.get("RUN_RECRUITING_TEMPORAL_TESTS") != "1", reason="Opt-in local Temporal"
)
@pytest.mark.asyncio
async def test_real_temporal_automation_http_timers_and_replay() -> None:
    from temporalio.client import Client
    from temporalio.worker import Replayer, Worker

    from services.api.app.settings import get_settings
    from services.worker.workflows.recruiting import RecruitingAutomationWorkflow

    executor = AsyncMock()
    executor.automation_step.side_effect = [1, 1, 0]
    activities = http_activities(executor)
    settings = get_settings()
    queue = "careeract-automation-test-" + uuid4().hex
    reference = str(uuid4())
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    try:
        async with Worker(
            client,
            task_queue=queue,
            workflows=[RecruitingAutomationWorkflow],
            activities=[activities.automation_step, activities.halt_automation],
        ):
            result = await client.start_workflow(
                RecruitingAutomationWorkflow.run,
                reference,
                id=queue,
                task_queue=queue,
            )
            await asyncio.wait_for(result.result(), timeout=40)
            assert executor.automation_step.await_count == 3
            history = await result.fetch_history()
            await Replayer(workflows=[RecruitingAutomationWorkflow]).replay_workflow(history)
    finally:
        await activities.client.aclose()


@integration
@pytest.mark.skipif(
    os.environ.get("RUN_RECRUITING_TEMPORAL_TESTS") != "1", reason="Opt-in local Temporal"
)
@pytest.mark.asyncio
async def test_real_temporal_read_worker_database_restore_and_replay(
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from temporalio.client import Client
    from temporalio.worker import Replayer, Worker

    from services.api.app.settings import get_settings
    from services.api.application.ports.boss_page import (
        BossConversationObservation,
        BossMessageObservation,
        BossPageObservation,
    )
    from services.api.infrastructure.recruiting_execution import RecruitingExecution
    from services.worker.workflows.recruiting import RecruitingReadWorkflow

    async with scenario.engine.begin() as db:
        version = await db.scalar(
            text(
                "UPDATE career.boss_connections SET status='connected', "
                "browser_session_id=:session "
                "WHERE id=:id RETURNING version"
            ),
            {"id": scenario.connection_id, "session": uuid4()},
        )
    service = ReadExecutionService(PostgresReadExecutionRepository(scenario.engine))
    accepted = await service.accept_boss(
        scenario.actor,
        connection_id=scenario.connection_id,
        expected_version=version,
        request_key=uuid4(),
    )
    settings = get_settings()
    control, reader = AsyncMock(), AsyncMock()
    reader.read_boss_page.return_value = BossPageObservation(
        "https://www.zhipin.com/web/geek/chat",
        "Synthetic-private",
        "conversations",
        "ready",
        (),
        (),
        (
            BossConversationObservation(
                "thread-1", "Synthetic-private", None, None, "Message", False, None
            ),
        ),
        (BossMessageObservation("m1", "recruiter", "Message", None, "thread-1"),),
    )
    executor = RecruitingExecution(scenario.engine, settings)
    activities = http_activities(executor)
    monkeypatch.setattr(executor, "signer", lambda: object())
    monkeypatch.setattr(
        "services.api.infrastructure.recruiting_execution.BrowserControlClient", lambda *_: control
    )
    monkeypatch.setattr(
        "services.api.infrastructure.recruiting_execution.BossPageClient", lambda *_: reader
    )
    queue = "careeract-read-test-" + uuid4().hex
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    async with Worker(
        client,
        task_queue=queue,
        workflows=[RecruitingReadWorkflow],
        activities=[activities.read, activities.stop_read],
    ):
        dispatcher = TemporalReadDispatcher(
            settings.temporal_address, settings.temporal_namespace, queue
        )
        await dispatcher.dispatch(accepted.task.id)
        handle = client.get_workflow_handle(f"careeract-read-{accepted.task.id}")
        await asyncio.wait_for(handle.result(), timeout=120)
        current = await service.read(scenario.actor, accepted.task.id)
        assert current is not None and current.task.status == "completed"
        assert current.authorization.expires_at == accepted.authorization.expires_at
        await dispatcher.dispatch(accepted.task.id)
        await activities.read(str(accepted.task.id))
        reader.read_boss_page.assert_awaited_once()
        history = await handle.fetch_history()
        assert "Synthetic-private" not in history.to_json()
        await Replayer(workflows=[RecruitingReadWorkflow]).replay_workflow(history)
        await scenario.engine.dispose()
        assert (
            await service.boss_result(scenario.actor, scenario.connection_id, accepted.task.id)
        ) is not None


@integration
@pytest.mark.skipif(
    os.environ.get("RUN_RECRUITING_TEMPORAL_TESTS") != "1", reason="Opt-in local Temporal"
)
@pytest.mark.asyncio
@pytest.mark.parametrize("delivery", ["completed", "unknown"])
async def test_real_temporal_send_single_attempt_restore_and_private_history(
    scenario: Scenario, monkeypatch: pytest.MonkeyPatch, delivery: str
) -> None:
    from temporalio.client import Client
    from temporalio.worker import Replayer, Worker

    from services.api.app.settings import get_settings
    from services.api.domain.communication_send import SendEvidence
    from services.api.infrastructure.communication_send import PostgresSendRepository
    from services.api.infrastructure.recruiting_execution import RecruitingExecution
    from services.worker.workflows.recruiting import RecruitingSendWorkflow
    from tests.api.test_communication_send import draft

    reply = await draft(scenario)
    repo = PostgresSendRepository(scenario.engine)
    send = await repo.accept(scenario.actor, reply.id, reply.version, uuid4())
    settings = get_settings()
    control, sender = AsyncMock(), AsyncMock()
    sender.send_message.return_value = SendEvidence(
        delivery, "m2" if delivery == "completed" else None
    )
    executor = RecruitingExecution(scenario.engine, settings)
    activities = http_activities(executor)
    monkeypatch.setattr(executor, "signer", lambda: object())
    monkeypatch.setattr(
        "services.api.infrastructure.recruiting_execution.BrowserControlClient", lambda *_: control
    )
    monkeypatch.setattr(
        "services.api.infrastructure.recruiting_execution.BossMessageSender", lambda *_: sender
    )
    queue = "careeract-send-test-" + uuid4().hex
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    async with Worker(
        client,
        task_queue=queue,
        workflows=[RecruitingSendWorkflow],
        activities=[activities.send_reply, activities.reconcile_send],
    ):
        dispatcher = TemporalReadDispatcher(
            settings.temporal_address,
            settings.temporal_namespace,
            queue,
            workflow_name="RecruitingSendWorkflow",
            id_prefix="careeract-send",
        )
        await dispatcher.dispatch(send.id)
        handle = client.get_workflow_handle(f"careeract-send-{send.id}")
        await asyncio.wait_for(handle.result(), timeout=120)
        result = await repo.get(scenario.actor, reply.id)
        assert result is not None and result.status == delivery and not result.cleanup_required
        assert result.expires_at == send.expires_at
        await dispatcher.dispatch(send.id)
        await activities.send_reply(str(send.id))
        sender.send_message.assert_awaited_once()
        history = await handle.fetch_history()
        assert reply.decision is not None
        assert reply.decision.text not in history.to_json()
        assert "您有 Python 经验吗" not in history.to_json()
        await Replayer(workflows=[RecruitingSendWorkflow]).replay_workflow(history)
        await scenario.engine.dispose()
        assert await repo.get(scenario.actor, reply.id) == result


@pytest.mark.asyncio
@pytest.mark.parametrize("physical", [None, "creating", "live"])
async def test_send_cleanup_revokes_before_inventory_even_if_registration_is_late(
    monkeypatch: pytest.MonkeyPatch, physical: str | None
) -> None:
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    from services.api.app.settings import get_settings
    from services.api.infrastructure.recruiting_execution import RecruitingExecution

    task, session = uuid4(), uuid4()
    row = {
        "user_id": "synthetic",
        "status": "running",
        "browser_session_id": session,
        "outcome": "send_attempted",
        "attempt": uuid4(),
        "request_id": uuid4(),
        "authorization": uuid4(),
        "expires_at": datetime.now(UTC),
    }
    events = []
    db = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.one_or_none.return_value = row
    db.execute.return_value = result

    async def inventory(*_: object) -> str | None:
        events.append("inventory")
        return physical

    db.scalar.side_effect = inventory
    engine = MagicMock()
    engine.connect.return_value.__aenter__.return_value = db
    control, repository = AsyncMock(), AsyncMock()

    async def revoke(*args: object) -> None:
        events.append(cast(str, args[1]))

    control.send.side_effect = revoke
    control.lifecycle.side_effect = revoke
    monkeypatch.setattr(
        "services.api.infrastructure.recruiting_execution.BrowserControlClient", lambda *_: control
    )
    monkeypatch.setattr(
        "services.api.infrastructure.recruiting_execution.PostgresSendRepository",
        lambda *_: repository,
    )
    executor = RecruitingExecution(engine, get_settings())
    monkeypatch.setattr(executor, "signer", lambda: object())
    await executor.reconcile_send(str(task))
    assert events == ["revoke", "inventory"] + (["release"] if physical is not None else [])
    assert repository.finish.await_args.args[1].state == "unknown"
