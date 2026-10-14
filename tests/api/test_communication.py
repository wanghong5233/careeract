import asyncio
import os
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from services.api.application.communication import generate_reply
from services.api.application.ports.boss_page import (
    BossConversationObservation,
    BossMessageObservation,
    BossPageObservation,
)
from services.api.application.read_execution import ReadExecutionService
from services.api.domain.communication import (
    CommunicationConflict,
    CommunicationInvalid,
    CommunicationNotFound,
    CommunicationReply,
    ReplyDecision,
    ReplyFact,
    validate_reply_decision,
)
from services.api.domain.profile import ProfileContent
from services.api.infrastructure.communication import PostgresCommunicationRepository, profile_facts
from services.api.infrastructure.profiles import PostgresProfileRepository
from services.api.infrastructure.read_execution import PostgresReadExecutionRepository
from tests.api.test_execution_semantics import Scenario
from tests.api.test_execution_semantics import scenario as scenario
from tests.browser.test_postgres_leases import database_url as database_url

integration = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL integration",
)
DECISION = ReplyDecision(
    "routine", "您好，我有 Python 项目经验。", "用户已确认的技能", (ReplyFact("skills", "Python"),)
)


@pytest.mark.parametrize(
    "decision",
    [
        replace(DECISION, facts=(ReplyFact("skills", "Java"),)),
        replace(DECISION, facts=(ReplyFact("salary", "Python"),)),
        replace(DECISION, facts=()),
        replace(DECISION, text=""),
        replace(DECISION, category="commitment"),
        replace(DECISION, category="resume_request", text="", facts=DECISION.facts),
        replace(DECISION, facts=(ReplyFact("goals", "Python"),)),
        replace(DECISION, facts=(ReplyFact("constraints", "Python"),)),
    ],
)
def test_invalid_facts_or_unresolved_sendable_text_are_rejected(decision: ReplyDecision) -> None:
    with pytest.raises(CommunicationInvalid):
        validate_reply_decision(
            decision, {"skills": "Python 项目经验", "goals": "Python", "constraints": "Python"}
        )


def test_known_and_unresolved_decisions_remain_distinct() -> None:
    assert validate_reply_decision(DECISION, {"skills": "Python 项目经验"}) == DECISION
    unknown = ReplyDecision("unknown", "", "缺少已确认职业背景", ())
    assert validate_reply_decision(unknown, {}) == unknown


def test_subjective_preferences_are_not_reply_fact_sources() -> None:
    content = ProfileContent(skills="Python", goals="寻找工作", constraints="需要远程办公")
    assert profile_facts(content) == {"skills": "Python"}


def test_legacy_acknowledgements_are_rejected_even_with_confirmed_facts() -> None:
    for reply_text in ["", "您好，感谢联系，请问可以介绍一下岗位职责和任职要求吗？"]:
        with pytest.raises(CommunicationInvalid):
            validate_reply_decision(
                ReplyDecision("acknowledgement", reply_text, "历史草稿", ()), {}
            )


@integration
@pytest.mark.asyncio
@pytest.mark.parametrize("when", ["before_claim", "after_claim"])
async def test_connection_revocation_fences_model_and_late_result(
    scenario: Scenario, when: str
) -> None:
    source = await read_source(scenario)
    reply = await accept(scenario, source)
    repo = PostgresCommunicationRepository(scenario.engine)
    claim = await repo.claim(reply.id) if when == "after_claim" else None
    async with scenario.engine.begin() as db:
        await db.execute(
            text(
                "UPDATE career.boss_connections SET status='revoked', version=:version WHERE id=:id"
            ),
            {"id": scenario.connection_id, "version": uuid4()},
        )
    if claim is not None:
        await repo.finish(claim, decision=DECISION, outcome="decision_completed")
    else:
        assert await repo.claim(reply.id) is None
    saved = await repo.get(scenario.actor, reply.id)
    assert saved.status == "cancelled" and saved.outcome == "connection_changed"
    assert saved.decision is None


@integration
@pytest.mark.asyncio
async def test_completed_decision_cannot_be_rewritten_by_cancel(scenario: Scenario) -> None:
    reply = await accept(scenario, await read_source(scenario))
    repo = PostgresCommunicationRepository(scenario.engine)
    claim = await repo.claim(reply.id)
    assert claim is not None
    await repo.finish(
        claim, decision=ReplyDecision("no_action", "", "无需回复", ()), outcome="decision_completed"
    )
    saved = await repo.get(scenario.actor, reply.id)
    with pytest.raises(CommunicationConflict):
        await repo.cancel(scenario.actor, reply.id, saved.version)
    assert await repo.get(scenario.actor, reply.id) == saved


async def read_source(s: Scenario, sender: str = "recruiter") -> UUID:
    async with s.engine.begin() as db:
        version = await db.scalar(
            text(
                "UPDATE career.boss_connections SET status='connected', "
                "browser_session_id=:session WHERE id=:id RETURNING version"
            ),
            {"id": s.connection_id, "session": uuid4()},
        )
    repository = PostgresReadExecutionRepository(s.engine)
    accepted = await ReadExecutionService(repository).accept_boss(
        s.actor,
        connection_id=s.connection_id,
        expected_version=version,
        request_key=uuid4(),
        conversation_id="thread-1",
    )
    await repository.reserve_browser(s.actor, accepted.task.id, uuid4())
    observation = BossPageObservation(
        "https://www.zhipin.com/web/geek/chat",
        "Synthetic",
        "conversations",
        "ready",
        (),
        (),
        (BossConversationObservation("thread-1", None, None, None, None, False, None, "m1"),),
        (BossMessageObservation("m1", "recruiter", "您有 Python 经验吗？", None, "thread-1"),),
    )
    if sender != "recruiter":
        observation = replace(
            observation,
            conversations=(replace(observation.conversations[0], last_message_id="m2"),),
            messages=(
                *observation.messages,
                BossMessageObservation("m2", "candidate", "已答复", None, "thread-1"),
            ),
        )
    await repository.finish_browser(
        s.actor, accepted.task.id, outcome="read_completed", observation=observation
    )
    return accepted.task.id


@integration
@pytest.mark.asyncio
async def test_information_card_after_verified_anchor_is_not_a_recruiter_prompt(
    scenario: Scenario,
) -> None:
    source = await read_source(scenario)
    async with scenario.engine.begin() as db:
        await db.execute(
            text(
                "UPDATE career.execution_read_results SET page=jsonb_set(page,'{messages}',"
                "(page->'messages') || CAST(:card AS jsonb)) WHERE task_id=:task"
            ),
            {
                "task": source,
                "card": '[{"message_id":"m3","sender":"recruiter",'
                '"content":"Synthetic information card","sent_at":null,'
                '"conversation_id":"thread-1"}]',
            },
        )
    reply = await accept(scenario, source)
    claim = await PostgresCommunicationRepository(scenario.engine).claim(reply.id)
    assert claim is not None
    assert claim.source.payload["messages"] == [
        {"sender": "recruiter", "content": "您有 Python 经验吗？"}
    ]
    with pytest.raises(CommunicationConflict):
        await PostgresCommunicationRepository(scenario.engine).accept(
            scenario.actor,
            connection_id=scenario.connection_id,
            read_task_id=source,
            conversation_id="thread-1",
            message_id="m3",
            request_key=uuid4(),
        )


async def accept(s: Scenario, source: UUID, key: UUID | None = None) -> CommunicationReply:
    return await PostgresCommunicationRepository(s.engine).accept(
        s.actor,
        connection_id=s.connection_id,
        read_task_id=source,
        conversation_id="thread-1",
        message_id="m1",
        request_key=key or uuid4(),
    )


@integration
@pytest.mark.asyncio
async def test_source_binding_replay_isolation_and_cancel_fencing(scenario: Scenario) -> None:
    source = await read_source(scenario)
    await PostgresProfileRepository(scenario.engine).save_confirmed(
        scenario.actor, ProfileContent(skills="Python 项目经验"), None
    )
    key = uuid4()
    replies = await asyncio.gather(*(accept(scenario, source, key) for _ in range(3)))
    assert all(reply == replies[0] for reply in replies)
    reply = replies[0]
    repo = PostgresCommunicationRepository(scenario.engine)
    with pytest.raises(CommunicationConflict):
        await accept(scenario, source)
    with pytest.raises(CommunicationNotFound):
        await repo.get(scenario.other, reply.id)
    with pytest.raises(CommunicationNotFound):
        await repo.list(scenario.other, scenario.connection_id)
    claims = await asyncio.gather(repo.claim(reply.id), repo.claim(reply.id))
    assert sum(claim is not None for claim in claims) == 1
    claim = next(claim for claim in claims if claim is not None)
    assert claim.source.profile_facts["skills"] == "Python 项目经验"
    running = await repo.get(scenario.actor, reply.id)
    with pytest.raises(CommunicationConflict):
        await repo.cancel(scenario.actor, reply.id, reply.version)
    cancelled = await repo.cancel(scenario.actor, reply.id, running.version)
    await repo.finish(claim, decision=DECISION, outcome="decision_completed")
    assert await repo.get(scenario.actor, reply.id) == cancelled
    assert (await accept(scenario, source, key)).status == "cancelled"
    assert await repo.claim(reply.id) is None


@integration
@pytest.mark.asyncio
async def test_crashed_claim_recovery_rejects_old_result_and_preserves_snapshot(
    scenario: Scenario,
) -> None:
    source = await read_source(scenario)
    profile = await PostgresProfileRepository(scenario.engine).save_confirmed(
        scenario.actor, ProfileContent(skills="Python 项目经验"), None
    )
    reply = await accept(scenario, source)
    repo = PostgresCommunicationRepository(scenario.engine)
    old = await repo.claim(reply.id)
    assert old is not None
    await PostgresProfileRepository(scenario.engine).save_confirmed(
        scenario.actor, ProfileContent(skills="Java"), profile.version
    )
    async with scenario.engine.begin() as db:
        await db.execute(
            text(
                "UPDATE career.communication_replies SET claim_expires_at=clock_timestamp() "
                "-interval '1 second' WHERE id=:id"
            ),
            {"id": reply.id},
        )
    fresh = await repo.claim(reply.id)
    assert fresh is not None and fresh.token != old.token
    assert fresh.source.profile_facts["skills"] == "Python 项目经验"
    await repo.finish(old, decision=DECISION, outcome="stale")
    assert (await repo.get(scenario.actor, reply.id)).status == "running"
    await repo.finish(fresh, decision=DECISION, outcome="decision_completed")
    saved = await repo.get(scenario.actor, reply.id)
    assert saved.status == "waiting" and saved.decision == DECISION
    await scenario.engine.dispose()
    assert await repo.get(scenario.actor, reply.id) == saved


@integration
@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["stale", "answered", "version", "foreign"])
async def test_unreliable_source_is_rejected(scenario: Scenario, invalid: str) -> None:
    source = await read_source(scenario, "candidate" if invalid == "answered" else "recruiter")
    async with scenario.engine.begin() as db:
        if invalid == "stale":
            await db.execute(
                text(
                    "UPDATE career.execution_read_results SET observed_at=clock_timestamp() "
                    "-interval '16 minutes' WHERE task_id=:id"
                ),
                {"id": source},
            )
        if invalid == "version":
            await db.execute(
                text("UPDATE career.boss_connections SET version=:version WHERE id=:id"),
                {"id": scenario.connection_id, "version": uuid4()},
            )
    with pytest.raises(CommunicationConflict):
        await accept(scenario, uuid4() if invalid == "foreign" else source)


@integration
@pytest.mark.asyncio
async def test_generation_validates_result_and_expired_task_cannot_publish(
    scenario: Scenario,
) -> None:
    source = await read_source(scenario)
    reply = await accept(scenario, source)
    repo = PostgresCommunicationRepository(scenario.engine)
    generator = AsyncMock()
    generator.generate.return_value = DECISION
    await generate_reply(repo, generator, reply.id)
    saved = await repo.get(scenario.actor, reply.id)
    assert saved.status == "failed" and saved.outcome == "invalid_model_result"
    assert saved.decision is None
    next_reply = await accept(scenario, source)
    async with scenario.engine.begin() as db:
        await db.execute(
            text(
                "UPDATE career.communication_replies SET expires_at=clock_timestamp() "
                "-interval '1 second' WHERE id=:id"
            ),
            {"id": next_reply.id},
        )
    generator.reset_mock()
    await generate_reply(repo, generator, next_reply.id)
    generator.generate.assert_not_awaited()
    assert (await repo.get(scenario.actor, next_reply.id)).status == "timed_out"


@integration
@pytest.mark.skipif(
    os.environ.get("RUN_RECRUITING_MODEL_TESTS") != "1",
    reason="Opt-in real configured model and local Temporal, synthetic career data only",
)
@pytest.mark.asyncio
async def test_real_temporal_agno_path_with_synthetic_source(scenario: Scenario) -> None:
    from temporalio.client import Client
    from temporalio.worker import Replayer, Worker

    from services.api.app.settings import get_settings
    from services.api.infrastructure.communication_dispatch import TemporalReplyDispatcher
    from services.api.infrastructure.recruiting_execution import RecruitingExecution
    from services.worker.workflows.recruiting import RecruitingReplyWorkflow
    from tests.api.test_recruiting_execution_http import http_activities

    source = await read_source(scenario)
    await PostgresProfileRepository(scenario.engine).save_confirmed(
        scenario.actor, ProfileContent(skills="Python 项目经验"), None
    )
    reply = await accept(scenario, source)
    settings = get_settings()
    queue = "careeract-reply-test-" + uuid4().hex
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    activities = http_activities(RecruitingExecution(scenario.engine, settings))
    async with Worker(
        client,
        task_queue=queue,
        workflows=[RecruitingReplyWorkflow],
        activities=[activities.generate],
    ):
        dispatch = TemporalReplyDispatcher(
            settings.temporal_address, settings.temporal_namespace, queue
        )
        await dispatch.dispatch(reply.id)
        handle = client.get_workflow_handle(f"careeract-reply-{reply.id}")
        await asyncio.wait_for(handle.result(), timeout=120)
        saved = await PostgresCommunicationRepository(scenario.engine).get(scenario.actor, reply.id)
        assert saved.status == "waiting", saved.outcome
        assert saved.decision is not None and saved.decision.category == "routine"
        assert saved.decision.facts and saved.decision.text
        history = await handle.fetch_history()
        encoded = history.to_json()
        assert "Python" not in encoded and "profile_facts" not in encoded
        await Replayer(workflows=[RecruitingReplyWorkflow]).replay_workflow(history)
