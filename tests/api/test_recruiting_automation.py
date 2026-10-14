import asyncio
from hashlib import sha256
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from sqlalchemy import text

from services.api.application.communication import generate_reply
from services.api.application.read_execution import ReadExecutionService
from services.api.application.recruiting_automation import RecruitingAutomationRunner
from services.api.domain.communication import CommunicationConflict, CommunicationNotFound
from services.api.domain.communication_send import SendEvidence
from services.api.domain.profile import ProfileContent
from services.api.domain.recruiting_automation import RecruitingAutomation
from services.api.infrastructure.communication import PostgresCommunicationRepository
from services.api.infrastructure.communication_send import PostgresSendRepository
from services.api.infrastructure.profiles import PostgresProfileRepository
from services.api.infrastructure.read_execution import PostgresReadExecutionRepository
from services.api.infrastructure.recruiting_automation import PostgresAutomationRepository
from services.browser.sessions.authentication import BrowserCommand, CommandRejected
from services.browser.sessions.message_permit import PostgresMessagePermit
from tests.api.test_communication import DECISION, integration, read_source
from tests.api.test_communication_send import draft
from tests.api.test_execution_semantics import Scenario
from tests.api.test_execution_semantics import scenario as scenario
from tests.browser.test_command_authentication import command_payload
from tests.browser.test_postgres_leases import database_url as database_url


async def delegation(s: Scenario, *, max_sends: int = 2) -> RecruitingAutomation:
    async with s.engine.connect() as db:
        version = await db.scalar(
            text("SELECT version FROM career.boss_connections WHERE id=:id"),
            {"id": s.connection_id},
        )
    return await PostgresAutomationRepository(s.engine).accept(
        s.actor, s.connection_id, version, uuid4(), ("thread-1",), max_sends, 30, 300
    )


@integration
@pytest.mark.asyncio
async def test_owned_scope_replay_and_single_active_delegation(scenario: Scenario) -> None:
    await read_source(scenario)
    repo = PostgresAutomationRepository(scenario.engine)
    original = await delegation(scenario)
    with pytest.raises(CommunicationNotFound):
        await repo.get(scenario.other, original.id)
    with pytest.raises(CommunicationConflict):
        await delegation(scenario)
    with pytest.raises(CommunicationConflict):
        await repo.stop(scenario.actor, original.id, uuid4())
    stopped = await repo.stop(scenario.actor, original.id, original.version)
    assert stopped.status == "waiting"
    assert await repo.claim(original.id) is None
    halted = await repo.halt(original.id)
    assert halted is not None and halted.status == "waiting"
    await repo.confirm_stop(scenario.actor, original.id)
    fresh = await delegation(scenario)
    assert fresh.id != original.id
    await repo.stop(scenario.actor, fresh.id, fresh.version)
    await repo.confirm_stop(scenario.actor, fresh.id)
    async with scenario.engine.connect() as db:
        version = await db.scalar(
            text("SELECT version FROM career.boss_connections WHERE id=:id"),
            {"id": scenario.connection_id},
        )
    key = uuid4()
    args = (scenario.actor, scenario.connection_id, version, key, ("thread-1",), 2, 30, 300)
    saved = await repo.accept(*args)
    assert await repo.accept(*args) == saved
    with pytest.raises(CommunicationConflict):
        await repo.accept(*args[:-1], 600)
    await repo.stop(scenario.actor, saved.id, saved.version)
    await repo.confirm_stop(scenario.actor, saved.id)
    with pytest.raises(CommunicationConflict):
        await repo.accept(
            scenario.actor, scenario.connection_id, version, uuid4(), ("unverified",), 2, 30, 300
        )


@integration
@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["expiry", "connection", "interrupted"])
async def test_expiry_connection_or_interruption_never_replays_stage(
    scenario: Scenario, change: str
) -> None:
    await read_source(scenario)
    repo = PostgresAutomationRepository(scenario.engine)
    task = await delegation(scenario)
    if change == "interrupted":
        first, second = await asyncio.gather(repo.claim(task.id), repo.claim(task.id))
        assert sum(step is not None for step in (first, second)) == 1
    else:
        async with scenario.engine.begin() as db:
            await db.execute(
                text(
                    "UPDATE career.recruiting_automations SET expires_at=clock_timestamp() "
                    "-interval '1 second' WHERE id=:id"
                    if change == "expiry"
                    else "UPDATE career.boss_connections SET version=:version WHERE id=:id"
                ),
                {
                    "id": task.id if change == "expiry" else scenario.connection_id,
                    "version": uuid4(),
                },
            )
        assert await repo.claim(task.id) is None
    assert await repo.claim(task.id) is None
    saved = await repo.get(scenario.actor, task.id)
    assert saved.status == ("timed_out" if change == "expiry" else "waiting")


@integration
@pytest.mark.asyncio
async def test_delegated_budget_replay_and_revoke_before_browser_consume(
    scenario: Scenario,
) -> None:
    reply = await draft(scenario)
    repo = PostgresAutomationRepository(scenario.engine)
    task = await delegation(scenario, max_sends=1)
    assert await repo.claim(task.id)
    await repo.finish(task.id, stage="send", reply=reply.id)
    assert await repo.claim(task.id)
    sends = PostgresSendRepository(scenario.engine)
    key = uuid4()
    action = await sends.accept(scenario.actor, reply.id, reply.version, key, automation_id=task.id)
    assert (
        await sends.accept(scenario.actor, reply.id, reply.version, key, automation_id=task.id)
        == action
    )
    assert (await repo.get(scenario.actor, task.id)).sends_reserved == 1
    claim = await sends.claim(action.id)
    assert claim is not None
    c = claim.context
    command = BrowserCommand.model_validate(
        command_payload()
        | {
            "action": "send_message",
            "owner_id": "boss-reply",
            "sub": c.user_id,
            "task_id": c.task_id,
            "attempt_id": c.attempt_id,
            "session_id": c.session_id,
            "authorization_id": c.authorization_id,
            "request_id": c.request_id,
            "conversation_id": c.conversation_id,
            "message_id": claim.message_id,
            "text_digest": sha256(claim.text.encode()).hexdigest(),
            "source_digest": sha256(claim.source_text.encode()).hexdigest(),
        }
    )
    await repo.stop(scenario.actor, task.id, task.version)
    with pytest.raises(CommandRejected):
        await PostgresMessagePermit(scenario.engine).consume(command)
    replay = await sends.accept(scenario.actor, reply.id, reply.version, key, automation_id=task.id)
    assert replay.id == action.id and replay.status == "running"
    assert (await repo.get(scenario.actor, task.id)).sends_reserved == 1


@integration
@pytest.mark.asyncio
@pytest.mark.parametrize("existing_draft", ["none", "fresh", "expired"])
async def test_staged_loop_uses_existing_decision_and_send_evidence(
    scenario: Scenario, existing_draft: str
) -> None:
    source = await read_source(scenario)
    await PostgresProfileRepository(scenario.engine).save_confirmed(
        scenario.actor, ProfileContent(skills="Python 项目经验"), None
    )
    repo = PostgresAutomationRepository(scenario.engine)
    task = await delegation(scenario, max_sends=1)
    reads = PostgresReadExecutionRepository(scenario.engine)
    replies = PostgresCommunicationRepository(scenario.engine)
    sends = PostgresSendRepository(scenario.engine)
    executor = AsyncMock()

    async def read(reference: str) -> None:
        from uuid import UUID

        async with scenario.engine.connect() as db:
            page = await db.scalar(
                text("SELECT page FROM career.execution_read_results WHERE task_id=:id"),
                {"id": source},
            )
        from services.api.application.ports.boss_page import BossPageObservation

        await reads.reserve_browser(scenario.actor, UUID(reference), uuid4())
        await reads.finish_browser(
            scenario.actor,
            UUID(reference),
            outcome="read_completed",
            observation=TypeAdapter(BossPageObservation).validate_python(page),
        )

    async def generate(reference: str) -> None:
        from uuid import UUID

        model = AsyncMock()
        model.generate.return_value = DECISION
        await generate_reply(replies, model, UUID(reference))

    async def send(reference: str) -> None:
        from uuid import UUID

        assert await sends.claim(UUID(reference)) is not None
        await sends.finish(UUID(reference), SendEvidence("completed", "m2"))

    executor.read.side_effect = read
    executor.generate.side_effect = generate
    executor.send_reply.side_effect = send
    if existing_draft != "none":
        from uuid import UUID

        async with scenario.engine.connect() as db:
            message_id = await db.scalar(
                text(
                    "SELECT page->'messages'->0->>'message_id' FROM "
                    "career.execution_read_results WHERE task_id=:id"
                ),
                {"id": source},
            )
        prior = await replies.accept(
            scenario.actor,
            connection_id=scenario.connection_id,
            read_task_id=UUID(str(source)),
            conversation_id="thread-1",
            message_id=message_id,
            request_key=uuid4(),
        )
        await generate(str(prior.id))
        if existing_draft == "expired":
            async with scenario.engine.begin() as db:
                await db.execute(
                    text(
                        "UPDATE career.communication_replies SET expires_at=clock_timestamp() "
                        "-interval '1 second' WHERE id=:id"
                    ),
                    {"id": prior.id},
                )
    runner = RecruitingAutomationRunner(repo, ReadExecutionService(reads), replies, sends, executor)
    assert await runner.step(task.id) == 1
    assert await runner.step(task.id) == 1
    assert await runner.step(task.id) == 0
    assert await runner.step(task.id) == 0
    assert (await repo.get(scenario.actor, task.id)).status == "completed"
    assert executor.send_reply.await_count == 1
    assert executor.generate.await_count == (0 if existing_draft == "fresh" else 1)
