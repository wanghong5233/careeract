import asyncio
import json
import os
from types import SimpleNamespace
from typing import cast
from unittest.mock import create_autospec

import pytest
from agno.run.base import RunContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.application.agent_context import AgentContextService
from services.api.application.context import ActorContext
from services.api.application.materials import MaterialService
from services.api.application.memories import MemoryService
from services.api.application.profiles import ProfileService
from services.api.application.projects import ProjectService
from services.api.application.work_sessions import AgentWorkSessionService
from services.api.domain.material import MaterialConflict, MaterialDraft, MaterialNotFound
from services.api.domain.material_review import review_body
from services.api.infrastructure.agent_tools import build_agent_tools, initialize_run_manifest
from services.api.infrastructure.materials import PostgresMaterialRepository
from tests.browser.test_postgres_leases import database_url as database_url


@pytest.mark.skipif(
    os.environ.get("RUN_MATERIAL_POSTGRES_TESTS") != "1", reason="Isolated PostgreSQL opt-in"
)
@pytest.mark.asyncio
async def test_partial_review_persistence_rewrite_concurrency_and_legacy(database_url: str) -> None:
    engine = create_async_engine(database_url)
    service = MaterialService(PostgresMaterialRepository(engine), enabled=True)
    actor = ActorContext("partial-review", "synthetic-review")
    other = ActorContext("partial-other", "synthetic-other")
    try:
        async with engine.begin() as connection:
            for owner in (actor, other):
                await connection.execute(
                    text(
                        'INSERT INTO auth."user" (id,name,email,"emailVerified") '
                        "VALUES (:id,:id,:email,false)"
                    ),
                    {"id": owner.user_id, "email": owner.user_id + "@example.invalid"},
                )
        detail = await service.create(
            actor,
            material_id=None,
            project_id=None,
            title="合成精细审阅",
            body="重复短语。合成职责。\n重复短语。成果待述🙂。",
            draft=None,
        )
        proposal = await service.propose(
            actor,
            detail.material.id,
            base_version_id=detail.current_version.id,
            proposed_body="重复短语。负责合成职责。\n重复短语。明确成果待述🙂。新增英文 API。",
            rationale="仅用合成输入",
        )
        assert len(proposal.changes) >= 3
        first, second, third = (str(change["id"]) for change in proposal.changes[:3])
        with pytest.raises(MaterialNotFound):
            await service.resolve(
                other,
                detail.material.id,
                proposal.id,
                state="accepted",
                change_ids=(first,),
                expected_version=proposal.review_version,
            )
        results = await asyncio.gather(
            *(
                service.resolve(
                    actor,
                    detail.material.id,
                    proposal.id,
                    state="accepted" if identifier == first else "rejected",
                    change_ids=(identifier,),
                    expected_version=proposal.review_version,
                )
                for identifier in (first, second)
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(result, MaterialConflict) for result in results) == 1
        current = await service.read(actor, detail.material.id)
        reviewed = current.proposals[0]
        decided = next(change for change in reviewed.changes if change["state"] != "pending")
        replay = await service.resolve(
            actor,
            detail.material.id,
            proposal.id,
            state=str(decided["state"]),
            change_ids=(str(decided["id"]),),
            expected_version=proposal.review_version,
        )
        assert len(replay.versions) == len(current.versions)
        remaining = second if decided["id"] == first else first
        current = await service.resolve(
            actor,
            detail.material.id,
            proposal.id,
            state="rejected" if remaining == second else "accepted",
            change_ids=(remaining,),
            expected_version=reviewed.review_version,
        )
        reviewed = current.proposals[0]
        assert reviewed.state == "pending" and current.current_version.number == 2
        assert current.current_version.body == review_body(
            proposal.base_body, list(reviewed.changes)
        )
        sessions = create_autospec(AgentWorkSessionService, instance=True)
        sessions.read.return_value = SimpleNamespace(project_id=None)
        context = AgentContextService(
            create_autospec(ProfileService, instance=True),
            create_autospec(ProjectService, instance=True),
            create_autospec(MemoryService, instance=True),
            sessions,
            service,
        )
        run = RunContext("synthetic-targeted", "synthetic-session", actor.user_id)
        initialize_run_manifest(run)
        tools = {tool.__name__: tool for tool in build_agent_tools(context)(run_context=run)}
        read_payload = json.loads(await tools["read_material"](str(detail.material.id)))
        assert read_payload["material"]["pending_draft"]["review_version"] == str(
            reviewed.review_version
        )
        original = cast(
            str, next(change["replacement"] for change in reviewed.changes if change["id"] == third)
        )
        result = json.loads(
            await tools["propose_material_edit"](
                str(detail.material.id),
                str(current.current_version.id),
                "合成定向改写🙂\nAPI",
                proposal_id=str(proposal.id),
                change_id=third,
                review_version=str(reviewed.review_version),
            )
        )
        assert result["status"] == "pending"
        rewritten = await service.read(actor, detail.material.id)
        assert rewritten.current_version == current.current_version
        changed = next(change for change in rewritten.proposals[0].changes if change["id"] == third)
        assert changed["state"] == "pending" and changed["replacement"] == "合成定向改写🙂\nAPI"
        revisions = cast(list[dict[str, object]], changed["revisions"])
        assert revisions[0]["replacement"] == original
        assert rewritten.proposals[0].changes[:2] == reviewed.changes[:2]
        with pytest.raises(MaterialConflict):
            await service.resolve(
                actor,
                detail.material.id,
                proposal.id,
                state="accepted",
                change_ids=(third,),
                expected_version=reviewed.review_version,
            )
        await service.save_version(
            actor,
            detail.material.id,
            base_version_id=current.current_version.id,
            body=current.current_version.body + "\n用户独立精确修正。",
        )
        with pytest.raises(MaterialConflict):
            await service.resolve(
                actor,
                detail.material.id,
                proposal.id,
                state="accepted",
                change_ids=(third,),
                expected_version=rewritten.proposals[0].review_version,
            )
        stale_rejected = await service.resolve(
            actor,
            detail.material.id,
            proposal.id,
            state="rejected",
            change_ids=(third,),
            expected_version=rewritten.proposals[0].review_version,
        )
        assert stale_rejected.current_version.number == 3
        draft = await service.create(
            actor,
            material_id=None,
            project_id=None,
            title="首份合成草稿",
            body="",
            draft=MaterialDraft("合成首稿🙂\nAPI", "合成首稿"),
        )
        assert len(draft.proposals[0].changes) == 1
        accepted = await service.resolve(
            actor,
            draft.material.id,
            draft.proposals[0].id,
            state="accepted",
            change_ids=(str(draft.proposals[0].changes[0]["id"]),),
            expected_version=draft.proposals[0].review_version,
        )
        assert (
            accepted.current_version.number == 1
            and accepted.current_version.body == "合成首稿🙂\nAPI"
        )
        legacy = await service.create(
            actor,
            material_id=None,
            project_id=None,
            title="合成旧接口",
            body="",
            draft=MaterialDraft("合成旧接口正文", "合成旧接口"),
        )
        legacy = await service.resolve(
            actor, legacy.material.id, legacy.proposals[0].id, state="accepted"
        )
        assert all(change["state"] == "accepted" for change in legacy.proposals[0].changes)
        with pytest.raises(MaterialConflict):
            await service.resolve(
                actor,
                legacy.material.id,
                legacy.proposals[0].id,
                state="rejected",
                change_ids=(str(legacy.proposals[0].changes[0]["id"]),),
                expected_version=legacy.proposals[0].review_version,
            )
    finally:
        await engine.dispose()
