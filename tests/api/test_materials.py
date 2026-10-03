import asyncio
import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import create_autospec
from uuid import uuid4

import pytest
from agno.run.base import RunContext
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.app.factory import create_app
from services.api.application.agent_context import AgentContextService
from services.api.application.context import ActorContext
from services.api.application.materials import MaterialService
from services.api.application.memories import MemoryService
from services.api.application.ports.materials import MaterialRepository
from services.api.application.profiles import ProfileService
from services.api.application.projects import ProjectService
from services.api.application.work_sessions import AgentWorkSessionService
from services.api.domain.material import (
    Material,
    MaterialConflict,
    MaterialDetail,
    MaterialDraft,
    MaterialNotFound,
    MaterialProposal,
    MaterialUnavailable,
    MaterialVersion,
)
from services.api.domain.privacy import RestrictedContent
from services.api.infrastructure.agent_tools import build_agent_tools, initialize_run_manifest
from services.api.infrastructure.materials import PostgresMaterialRepository
from services.api.infrastructure.work_sessions import PostgresAgentWorkSessionRepository
from tests.api.test_health import build_settings, use_signing_key
from tests.api.test_memories import RuntimeOnly, token_for
from tests.browser.test_postgres_leases import database_url as database_url


def test_material_auth_validation_and_default_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Ed25519PrivateKey.generate()
    use_signing_key(monkeypatch, key)
    app = create_app(build_settings(), lambda _settings: RuntimeOnly())
    headers = {"Authorization": "Bearer " + token_for(key, "synthetic-user")}
    with TestClient(app) as client:
        assert client.get("/api/v1/materials").status_code == 401
        assert client.get("/api/v1/materials", headers=headers).status_code == 503
        for body in (
            {"title": "PRIVATE_MARKER" * 50, "body": "内容"},
            {"title": "标题", "body": "内容", "user_id": "other"},
            {"title": "标题", "body": "内容", "state": "accepted"},
        ):
            response = client.post("/api/v1/materials", headers=headers, json=body)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "invalid_material"
            assert "PRIVATE_MARKER" not in response.text
            assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_material_privacy_before_repository_and_default_gate() -> None:
    repository = create_autospec(MaterialRepository, instance=True)
    actor = ActorContext("synthetic", "run")
    with pytest.raises(MaterialUnavailable):
        await MaterialService(repository).list(actor, project_id=None, limit=20)
    service = MaterialService(repository, enabled=True)
    with pytest.raises(RestrictedContent):
        await service.create(
            actor,
            material_id=None,
            project_id=None,
            title="合成",
            body="",
            draft=MaterialDraft("密码: synthetic-only", ""),
        )
    with pytest.raises(RestrictedContent):
        await service.propose(
            actor,
            uuid4(),
            base_version_id=uuid4(),
            proposed_body="合成",
            rationale="密码: synthetic-only",
        )
    repository.create.assert_not_awaited()
    repository.create_proposal.assert_not_awaited()


def synthetic_material_detail() -> MaterialDetail:
    material_id, version_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    material = Material(
        material_id, "synthetic", None, "合成材料", "active", version_id, uuid4(), now, now
    )
    version = MaterialVersion(version_id, material_id, 0, "", "seed", now)
    proposal = MaterialProposal(
        uuid4(), material_id, version_id, "合成待审阅表达", "合成", "pending", now, None, "", 0
    )
    return MaterialDetail(material, version, (version,), (proposal,))


@pytest.mark.asyncio
async def test_material_draft_feedback_records_unconfirmed_basis_and_never_accepts() -> None:
    materials = create_autospec(MaterialService, instance=True)
    sessions = create_autospec(AgentWorkSessionService, instance=True)
    sessions.read.return_value = SimpleNamespace(project_id=None)
    detail = synthetic_material_detail()
    materials.read.return_value = detail
    materials.propose.return_value = detail.proposals[0]
    context = AgentContextService(
        create_autospec(ProfileService, instance=True),
        create_autospec(ProjectService, instance=True),
        create_autospec(MemoryService, instance=True),
        sessions,
        materials,
    )
    run = RunContext("material-run", "session", "synthetic")
    initialize_run_manifest(run)
    tools = {tool.__name__: tool for tool in build_agent_tools(context)(run_context=run)}
    payload = json.loads(await tools["read_material"](str(detail.material.id)))
    assert payload["material"]["body"] == ""
    assert payload["material"]["pending_draft"]["status"] == "unconfirmed_expression"
    assert payload["material"]["pending_draft"]["id"] == str(detail.proposals[0].id)
    result = json.loads(
        await tools["propose_material_edit"](
            str(detail.material.id), str(detail.current_version.id), "根据反馈改写", "合成"
        )
    )
    assert result["status"] == "pending"
    assert materials.propose.await_args.args[0].user_id == "synthetic"
    assert materials.propose.await_args.kwargs["references"][1]["type"] == "material_draft"
    materials.resolve.assert_not_awaited()
    assert "resolve" not in tools
    assert "PRIVATE_MARKER" not in await tools["read_material"]("PRIVATE_MARKER")
    with pytest.raises(MaterialNotFound):
        materials.read.return_value = replace(
            detail, material=replace(detail.material, project_id=uuid4())
        )
        await context.read_material(
            ActorContext("synthetic", "run"), session_id="session", material_id=detail.material.id
        )
    materials.read.return_value = replace(
        detail,
        proposals=(replace(detail.proposals[0], proposed_body="密码: synthetic-only"),),
    )
    result = await tools["read_material"](str(detail.material.id))
    assert json.loads(result)["status"] == "unavailable" and "synthetic-only" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("obsolete", ["rejected", "stale"])
async def test_material_feedback_excludes_resolved_and_stale_drafts(obsolete: str) -> None:
    materials = create_autospec(MaterialService, instance=True)
    sessions = create_autospec(AgentWorkSessionService, instance=True)
    sessions.read.return_value = SimpleNamespace(project_id=None)
    detail = synthetic_material_detail()
    proposal = (
        replace(detail.proposals[0], state="rejected")
        if obsolete == "rejected"
        else replace(detail.proposals[0], base_version_id=uuid4())
    )
    materials.read.return_value = replace(detail, proposals=(proposal,))
    context = AgentContextService(
        create_autospec(ProfileService, instance=True),
        create_autospec(ProjectService, instance=True),
        create_autospec(MemoryService, instance=True),
        sessions,
        materials,
    )
    payload = await context.read_material(
        ActorContext("synthetic", "run"), session_id="session", material_id=detail.material.id
    )
    material = payload["material"]
    assert isinstance(material, dict) and material["pending_draft"] is None


@pytest.mark.skipif(
    os.environ.get("RUN_MATERIAL_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL materials",
)
@pytest.mark.asyncio
async def test_material_draft_review_isolation_versions_and_replays(database_url: str) -> None:
    engine = create_async_engine(database_url)
    service = MaterialService(PostgresMaterialRepository(engine), enabled=True)
    first, second = ActorContext("material-first", "run"), ActorContext("material-second", "run")
    refs = ({"type": "profile", "title": "合成已确认背景", "version": str(uuid4())},)
    try:
        async with engine.begin() as connection:
            for actor in (first, second):
                await connection.execute(
                    text(
                        'INSERT INTO auth."user" (id,name,email,"emailVerified") '
                        "VALUES (:id,:id,:email,false)"
                    ),
                    {"id": actor.user_id, "email": actor.user_id + "@example.invalid"},
                )
        material_id = uuid4()
        draft = MaterialDraft("负责合成服务的接口设计。\n完成合成验证。", "整理职责", refs)
        detail = await service.create(
            first,
            material_id=material_id,
            project_id=None,
            title="合成项目讲述",
            body="",
            draft=draft,
        )
        assert detail.current_version.number == 0 and detail.current_version.body == ""
        proposal = detail.proposals[0]
        assert proposal.state == "pending" and proposal.references == refs
        assert "+负责合成服务的接口设计。" in service.diff(detail, proposal)
        assert (
            await service.create(
                first,
                material_id=material_id,
                project_id=None,
                title="合成项目讲述",
                body="",
                draft=draft,
            )
        ) == detail
        with pytest.raises(MaterialNotFound):
            await service.read(second, material_id)
        with pytest.raises(MaterialNotFound):
            await service.resolve(second, material_id, proposal.id, state="accepted")
        accepted = await service.resolve(first, material_id, proposal.id, state="accepted")
        assert accepted.current_version.number == 1
        assert accepted.current_version.body == draft.body
        assert accepted.current_version.references == refs
        again = await service.resolve(first, material_id, proposal.id, state="accepted")
        assert len(again.versions) == 2
        changed = await service.propose(
            first,
            material_id,
            base_version_id=accepted.current_version.id,
            proposed_body="改进合成表达。",
            rationale="聚焦职责",
            references=refs,
        )
        replay = await service.propose(
            first,
            material_id,
            base_version_id=accepted.current_version.id,
            proposed_body="改进合成表达。",
            rationale="聚焦职责",
            references=refs,
        )
        assert replay.id == changed.id
        updated = await service.save_version(
            first,
            material_id,
            base_version_id=accepted.current_version.id,
            body="用户精确修正合成事实。",
        )
        with pytest.raises(MaterialConflict):
            await service.resolve(first, material_id, changed.id, state="accepted")
        assert "-负责合成服务的接口设计。" in service.diff(updated, updated.proposals[0])
        rejected = await service.resolve(first, material_id, changed.id, state="rejected")
        assert rejected.current_version.id == updated.current_version.id
        assert rejected.proposals[0].state == "rejected"
        with pytest.raises(MaterialConflict):
            await service.save_version(
                first, material_id, base_version_id=accepted.current_version.id, body="不能覆盖"
            )
        assert not (await service.list(second, project_id=None, limit=20)).items
        assert len((await service.list(first, project_id=None, limit=20)).items) == 1
        async with engine.begin() as connection:
            await connection.execute(
                text('DELETE FROM auth."user" WHERE id=:id'), {"id": first.user_id}
            )
        assert not (await service.list(first, project_id=None, limit=20)).items
    finally:
        await engine.dispose()


@pytest.mark.skipif(
    os.environ.get("RUN_MATERIAL_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated PostgreSQL concurrency and scope",
)
@pytest.mark.asyncio
async def test_material_concurrent_acceptance_scope_and_pagination(database_url: str) -> None:
    engine = create_async_engine(database_url)
    service = MaterialService(PostgresMaterialRepository(engine), enabled=True)
    actor = ActorContext("material-race", "run")
    sessions = AgentWorkSessionService(PostgresAgentWorkSessionRepository(engine))
    context = AgentContextService(
        create_autospec(ProfileService, instance=True),
        create_autospec(ProjectService, instance=True),
        create_autospec(MemoryService, instance=True),
        sessions,
        service,
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    'INSERT INTO auth."user" (id,name,email,"emailVerified") '
                    "VALUES (:id,:id,'material-race@example.invalid',false)"
                ),
                {"id": actor.user_id},
            )
            project_id = uuid4()
            await connection.execute(
                text(
                    "INSERT INTO career.career_projects (id,user_id,title,purpose,status,version) "
                    "VALUES (:id,:user_id,'合成项目','','active',:version)"
                ),
                {"id": project_id, "user_id": actor.user_id, "version": uuid4()},
            )
        detail = await service.create(
            actor, material_id=None, project_id=project_id, title="并发材料", body="当前正文"
        )
        await sessions.associate(actor, session_id="material-session", project_id=None)
        with pytest.raises(MaterialNotFound):
            await context.read_material(
                actor, session_id="material-session", material_id=detail.material.id
            )
        assert (await context.list_materials(actor, session_id="material-session"))["items"] == []
        await sessions.associate(actor, session_id="material-session", project_id=project_id)
        assert (
            await context.read_material(
                actor, session_id="material-session", material_id=detail.material.id
            )
        )["status"] == "ok"
        one = await service.propose(
            actor,
            detail.material.id,
            base_version_id=detail.current_version.id,
            proposed_body="第一条修改",
            rationale="",
        )
        two = await service.propose(
            actor,
            detail.material.id,
            base_version_id=detail.current_version.id,
            proposed_body="第二条修改",
            rationale="",
        )
        results = await asyncio.gather(
            service.resolve(actor, detail.material.id, one.id, state="accepted"),
            service.resolve(actor, detail.material.id, two.id, state="accepted"),
            return_exceptions=True,
        )
        assert sum(isinstance(item, MaterialConflict) for item in results) == 1
        assert len((await service.read(actor, detail.material.id)).versions) == 2
        for index in range(3):
            await service.create(
                actor, material_id=None, project_id=None, title=f"材料 {index}", body="合成正文"
            )
        first = await service.list(actor, project_id=None, limit=2)
        next_page = await service.list(actor, project_id=None, limit=2, cursor=first.next_cursor)
        assert first.next_cursor and next_page.next_cursor is None
        assert len({item.id for item in first.items + next_page.items}) == 4
    finally:
        await engine.dispose()
