import asyncio
from dataclasses import replace
from hashlib import sha256
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import text

from services.api.application.communication_send import CommunicationSendService, execute_send
from services.api.application.ports.browser_control import BrowserControlUncertain
from services.api.application.ports.communication_send import SendClaim
from services.api.domain.communication import (
    ACKNOWLEDGEMENT_TEXT,
    CommunicationConflict,
    CommunicationNotFound,
    CommunicationReply,
    ReplyDecision,
)
from services.api.domain.communication_send import SendEvidence
from services.api.domain.execution import ExecutionConflict, ExecutionUnavailable
from services.api.domain.profile import ProfileContent
from services.api.infrastructure.communication import PostgresCommunicationRepository
from services.api.infrastructure.communication_send import PostgresSendRepository
from services.api.infrastructure.profiles import PostgresProfileRepository
from services.api.infrastructure.read_execution import PostgresReadExecutionRepository
from services.browser.sessions.authentication import BrowserCommand, CommandRejected
from services.browser.sessions.message_permit import PostgresMessagePermit
from tests.api.test_browser_control import control_context
from tests.api.test_communication import DECISION, accept, integration, read_source
from tests.api.test_execution_semantics import Scenario
from tests.api.test_execution_semantics import scenario as scenario
from tests.browser.test_command_authentication import command_payload
from tests.browser.test_postgres_leases import database_url as database_url


async def draft(s: Scenario) -> CommunicationReply:
    await PostgresProfileRepository(s.engine).save_confirmed(
        s.actor, ProfileContent(skills="Python 项目经验"), None
    )
    reply = await accept(s, await read_source(s))
    replies = PostgresCommunicationRepository(s.engine)
    claim = await replies.claim(reply.id)
    assert claim is not None
    await replies.finish(claim, decision=DECISION, outcome="decision_completed")
    s.actor = replace(s.actor, request_id=str(uuid4()))
    return await replies.get(s.actor, reply.id)


@integration
@pytest.mark.asyncio
@pytest.mark.parametrize("attempted", [False, True])
async def test_expired_draft_can_refresh_only_without_external_send_ledger(
    scenario: Scenario, attempted: bool
) -> None:
    reply = await draft(scenario)
    if attempted:
        await PostgresSendRepository(scenario.engine).accept(
            scenario.actor, reply.id, reply.version, uuid4()
        )
    async with scenario.engine.begin() as db:
        await db.execute(
            text(
                "UPDATE career.communication_replies SET expires_at=clock_timestamp() "
                "-interval '1 second' WHERE id=:id"
            ),
            {"id": reply.id},
        )
    replies = PostgresCommunicationRepository(scenario.engine)
    saved = await replies.get(scenario.actor, reply.id)
    assert saved.status == ("waiting" if attempted else "timed_out")
    if attempted:
        with pytest.raises(CommunicationConflict):
            await accept(scenario, reply.read_task_id)
        async with scenario.engine.begin() as db:
            await db.execute(
                text("UPDATE career.communication_replies SET status='cancelled' WHERE id=:id"),
                {"id": reply.id},
            )
        with pytest.raises(CommunicationConflict):
            await accept(scenario, reply.read_task_id)
    else:
        fresh = await accept(scenario, reply.read_task_id)
        assert fresh.id != reply.id and fresh.status == "accepted"
        assert (await replies.get(scenario.actor, reply.id)).decision == reply.decision


@integration
@pytest.mark.asyncio
async def test_neutral_acknowledgement_uses_same_source_bound_send_ledger(
    scenario: Scenario,
) -> None:
    reply = await accept(scenario, await read_source(scenario))
    replies = PostgresCommunicationRepository(scenario.engine)
    claim = await replies.claim(reply.id)
    assert claim is not None
    await replies.finish(
        claim,
        decision=ReplyDecision("acknowledgement", ACKNOWLEDGEMENT_TEXT, "请求岗位详情", ()),
        outcome="decision_completed",
    )
    reply = await replies.get(scenario.actor, reply.id)
    repo = PostgresSendRepository(scenario.engine)
    scenario.actor = replace(scenario.actor, request_id=str(uuid4()))
    action = await repo.accept(scenario.actor, reply.id, reply.version, uuid4())
    send = await repo.claim(action.id)
    assert send is not None and send.text == ACKNOWLEDGEMENT_TEXT
    await repo.finish(action.id, SendEvidence("unknown"))
    assert await repo.claim(action.id) is None


@integration
@pytest.mark.asyncio
async def test_send_authorization_is_owned_source_bound_and_single_use(scenario: Scenario) -> None:
    reply = await draft(scenario)
    repo = PostgresSendRepository(scenario.engine)
    key = uuid4()
    with pytest.raises(CommunicationConflict):
        await repo.accept(scenario.actor, reply.id, uuid4(), key)
    with pytest.raises(CommunicationNotFound):
        await repo.accept(scenario.other, reply.id, reply.version, key)
    actions = await asyncio.gather(
        *(repo.accept(scenario.actor, reply.id, reply.version, key) for _ in range(3))
    )
    assert actions[0] == actions[1] == actions[2]
    with pytest.raises(CommunicationConflict):
        await repo.accept(scenario.actor, reply.id, reply.version, uuid4())
    with pytest.raises(CommunicationConflict):
        await PostgresCommunicationRepository(scenario.engine).cancel(
            scenario.actor, reply.id, reply.version
        )
    claims = await asyncio.gather(repo.claim(actions[0].id), repo.claim(actions[0].id))
    assert sum(c is not None for c in claims) == 1
    claim = next(c for c in claims if c is not None)
    assert claim.source_text == "您有 Python 经验吗？" and claim.text == DECISION.text
    await repo.finish(actions[0].id, SendEvidence("unknown"))
    assert await repo.claim(actions[0].id) is None
    # Replaying authorization only returns unknown; it cannot recreate the task.
    assert (await repo.accept(scenario.actor, reply.id, reply.version, key)).status == "unknown"
    with pytest.raises(CommunicationConflict):
        await repo.cancel(scenario.actor, reply.id)
    saved = await repo.get(scenario.actor, reply.id)
    assert saved is not None and saved.status == "unknown"


@integration
@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["expired", "connection", "source", "profile"])
async def test_claim_rechecks_current_permission_and_context(
    scenario: Scenario, changed: str
) -> None:
    reply = await draft(scenario)
    repo = PostgresSendRepository(scenario.engine)
    action = await repo.accept(scenario.actor, reply.id, reply.version, uuid4())
    async with scenario.engine.begin() as db:
        sql = {
            "expired": "UPDATE career.execution_authorizations SET expires_at=clock_timestamp() "
            "-interval '1 second' WHERE task_id=:id",
            "connection": "UPDATE career.boss_connections SET version=:version "
            "WHERE id=:connection",
            "source": "UPDATE career.communication_replies SET expires_at=clock_timestamp() "
            "-interval '1 second' WHERE id=:reply",
            "profile": "UPDATE career.profiles SET version=:version WHERE user_id=:user",
        }[changed]
        await db.execute(
            text(sql),
            {
                "id": action.id,
                "version": uuid4(),
                "connection": scenario.connection_id,
                "reply": reply.id,
                "user": scenario.actor.user_id,
            },
        )
    assert await repo.claim(action.id) is None
    saved = await repo.get(scenario.actor, reply.id)
    assert saved is not None and saved.status == "failed"


@integration
@pytest.mark.asyncio
async def test_cancelled_queued_send_does_not_redispatch_or_renew(scenario: Scenario) -> None:
    reply = await draft(scenario)
    repo, dispatcher = PostgresSendRepository(scenario.engine), AsyncMock()
    service = CommunicationSendService(repo, dispatcher)
    dispatcher.dispatch.side_effect = ExecutionUnavailable("dispatch lost")
    with pytest.raises(ExecutionUnavailable):
        await service.authorize(scenario.actor, reply.id, reply.version, uuid4())
    accepted = await repo.get(scenario.actor, reply.id)
    dispatcher.dispatch.side_effect = None
    assert await service.resume(scenario.actor, reply.id) == accepted
    cancelled = await service.cancel(scenario.actor, reply.id)
    assert cancelled.status == "cancelled"
    assert await service.resume(scenario.actor, reply.id) == cancelled
    assert dispatcher.dispatch.await_count == 2
    assert await repo.claim(cancelled.id) is None
    assert cancelled.expires_at == accepted.expires_at


@integration
@pytest.mark.asyncio
async def test_completed_evidence_survives_cleanup_failure_and_cannot_be_rewritten(
    scenario: Scenario,
) -> None:
    reply = await draft(scenario)
    repo = PostgresSendRepository(scenario.engine)
    action = await repo.accept(scenario.actor, reply.id, reply.version, uuid4())
    assert await repo.claim(action.id) is not None
    await repo.finish(action.id, SendEvidence("completed", "123", True))
    saved = await repo.get(scenario.actor, reply.id)
    assert saved is not None
    assert saved.status == "completed" and saved.cleanup_required
    await repo.finish(action.id, SendEvidence("failed"))
    final = await repo.get(scenario.actor, reply.id)
    assert final is not None
    assert final.status == "completed" and final.evidence_message_id == "123"
    assert not final.cleanup_required


@integration
@pytest.mark.asyncio
async def test_permit_commit_is_single_use_and_rejects_wrong_bindings(scenario: Scenario) -> None:
    reply = await draft(scenario)
    repo = PostgresSendRepository(scenario.engine)
    action = await repo.accept(scenario.actor, reply.id, reply.version, uuid4())
    claim = await repo.claim(action.id)
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
    permit = PostgresMessagePermit(scenario.engine)
    for field, value in (
        ("sub", scenario.other.user_id),
        ("message_id", "wrong"),
        ("text_digest", "0" * 64),
        ("request_id", uuid4()),
        ("conversation_id", "other"),
    ):
        with pytest.raises(CommandRejected):
            await permit.consume(command.model_copy(update={field: value}))
    results = await asyncio.gather(
        permit.consume(command), permit.consume(command), return_exceptions=True
    )
    assert sum(r is None for r in results) == 1
    assert sum(isinstance(r, CommandRejected) for r in results) == 1
    async with scenario.engine.connect() as db:
        assert (
            await db.scalar(
                text("SELECT outcome FROM career.execution_attempts WHERE task_id=:id"),
                {"id": action.id},
            )
            == "send_attempted"
        )


@integration
@pytest.mark.asyncio
async def test_send_blocks_concurrent_read_and_unknown_blocks_next_send(scenario: Scenario) -> None:
    reply = await draft(scenario)
    repo = PostgresSendRepository(scenario.engine)
    action = await repo.accept(scenario.actor, reply.id, reply.version, uuid4())
    async with scenario.engine.connect() as db:
        version = await db.scalar(
            text("SELECT version FROM career.boss_connections WHERE id=:id"),
            {"id": scenario.connection_id},
        )
    from datetime import timedelta

    from services.api.domain.execution import BossReadTarget

    with pytest.raises(ExecutionConflict):
        await PostgresReadExecutionRepository(scenario.engine).accept(
            scenario.actor,
            target=BossReadTarget(scenario.connection_id, version, "thread-1"),
            request_key=uuid4(),
            authorization_lifetime=timedelta(minutes=5),
        )
    assert action.status == "accepted"


@integration
@pytest.mark.asyncio
@pytest.mark.parametrize("evidence", ["matching", "absent", "duplicate", "other_source", "old"])
async def test_unknown_send_reconciles_only_unique_delivery_from_later_owned_read(
    scenario: Scenario, evidence: str
) -> None:
    from services.api.application.ports.boss_page import (
        BossConversationObservation,
        BossMessageObservation,
        BossPageObservation,
    )
    from services.api.application.read_execution import ReadExecutionService

    reply = await draft(scenario)
    repo = PostgresSendRepository(scenario.engine)
    action = await repo.accept(scenario.actor, reply.id, reply.version, uuid4())
    assert await repo.claim(action.id) is not None
    await repo.finish(action.id, SendEvidence("unknown"))
    scenario.actor = replace(scenario.actor, request_id=str(uuid4()))
    reads = PostgresReadExecutionRepository(scenario.engine)
    async with scenario.engine.connect() as db:
        version = await db.scalar(
            text("SELECT version FROM career.boss_connections WHERE id=:id"),
            {"id": scenario.connection_id},
        )
    read = await ReadExecutionService(reads).accept_boss(
        scenario.actor,
        connection_id=scenario.connection_id,
        expected_version=version,
        request_key=uuid4(),
        conversation_id="thread-1",
    )
    await reads.reserve_browser(scenario.actor, read.task.id, uuid4())
    messages = [
        BossMessageObservation(
            "m1",
            "recruiter",
            "changed" if evidence == "other_source" else "您有 Python 经验吗？",
            None,
            "thread-1",
        )
    ]
    if evidence != "absent":
        messages.append(BossMessageObservation("m2", "candidate", DECISION.text, None, "thread-1"))
    if evidence == "duplicate":
        messages.append(BossMessageObservation("m3", "candidate", DECISION.text, None, "thread-1"))
    await reads.finish_browser(
        scenario.actor,
        read.task.id,
        outcome="read_completed",
        observation=BossPageObservation(
            "https://www.zhipin.com/web/geek/chat",
            "Synthetic",
            "conversations",
            "ready",
            (),
            (),
            (BossConversationObservation("thread-1", None, None, None, None, False, None),),
            tuple(messages),
        ),
    )
    if evidence == "old":
        async with scenario.engine.begin() as db:
            await db.execute(
                text(
                    "UPDATE career.execution_read_results SET observed_at=clock_timestamp() "
                    "-interval '20 minutes' WHERE task_id=:id"
                ),
                {"id": read.task.id},
            )
    with pytest.raises(CommunicationNotFound):
        await repo.reconcile(scenario.other, reply.id, read.task.id)
    if evidence == "matching":
        result = await repo.reconcile(scenario.actor, reply.id, read.task.id)
        assert result.status == "completed" and result.evidence_message_id == "m2"
        assert await repo.claim(action.id) is None
        assert await repo.reconcile(scenario.actor, reply.id, read.task.id) == result
    else:
        with pytest.raises(CommunicationConflict):
            await repo.reconcile(scenario.actor, reply.id, read.task.id)
        remaining = await repo.get(scenario.actor, reply.id)
        assert remaining is not None and remaining.status == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("result", ["completed", "unknown", "cleanup"])
async def test_execution_does_not_retry_and_preserves_delivery_during_cleanup(result: str) -> None:
    repo, control, sender = AsyncMock(), AsyncMock(), AsyncMock()
    repo.claim.return_value = SendClaim(
        replace(control_context(), conversation_id="thread-1"),
        "123",
        "Synthetic incoming",
        "Synthetic reply",
    )
    sender.send_message.return_value = SendEvidence("completed", "124")
    if result == "unknown":
        sender.send_message.side_effect = BrowserControlUncertain("response lost")
    if result == "cleanup":
        control.send.side_effect = [None, BrowserControlUncertain("release lost")]
        with pytest.raises(ExecutionUnavailable):
            await execute_send(repo, uuid4(), control, sender)
        evidence = repo.finish.await_args.args[1]
        assert evidence.state == "completed" and evidence.cleanup_required
    else:
        await execute_send(repo, uuid4(), control, sender)
        assert repo.finish.await_args.args[1].state == result
    assert sender.send_message.await_count == 1
    assert control.lifecycle.await_args_list[0].args[1] == "create"
