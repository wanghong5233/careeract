import json
from dataclasses import asdict
from uuid import NAMESPACE_URL, UUID, uuid5

from services.api.application.context import ActorContext
from services.api.application.materials import MaterialService
from services.api.application.memories import MemoryService
from services.api.application.profiles import ProfileService
from services.api.application.projects import ProjectService
from services.api.application.work_sessions import AgentWorkSessionService
from services.api.domain.material import MaterialDraft, MaterialInvalid, MaterialNotFound
from services.api.domain.memory import MemoryInvalid, MemoryNotFound, WorkspaceMemory
from services.api.domain.privacy import ensure_career_content

MAX_CONTEXT_CHARS = 64_000


def serialize_memory(memory: WorkspaceMemory) -> dict[str, object]:
    return {
        "id": str(memory.id),
        "version": str(memory.version),
        "kind": memory.kind,
        "state": memory.state,
        "title": memory.title,
        "content": memory.content,
        "source": memory.source,
        "project_id": str(memory.project_id) if memory.project_id else None,
    }


def encode_context(value: dict[str, object]) -> str:
    ensure_career_content(value)
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > MAX_CONTEXT_CHARS:
        raise MemoryInvalid("Context exceeds the run limit; no partial rules were disclosed")
    return encoded


class AgentContextService:
    def __init__(
        self,
        profiles: ProfileService,
        projects: ProjectService,
        memories: MemoryService,
        sessions: AgentWorkSessionService,
        materials: MaterialService | None = None,
    ) -> None:
        self.profiles, self.projects, self.materials = profiles, projects, materials
        self.memories, self.sessions = memories, sessions

    async def read(
        self, actor: ActorContext, *, session_id: str, include_profile: bool
    ) -> dict[str, object]:
        session = await self.sessions.read(actor, session_id=session_id)
        project = (
            await self.projects.read(actor, session.project_id) if session.project_id else None
        )
        rules = await self.memories.effective_rules(actor, project_id=session.project_id)
        profile = await self.profiles.read(actor) if include_profile else None
        basis: list[dict[str, str]] = []
        if project:
            basis.append(
                {
                    "type": "project",
                    "id": str(project.id),
                    "title": project.title,
                    "version": str(project.version),
                }
            )
        if profile:
            basis.append(
                {
                    "type": "profile",
                    "title": "已确认职业背景",
                    "version": str(profile.version),
                }
            )
        basis.extend(
            {"type": "rule", "id": str(rule.id), "title": rule.title, "version": str(rule.version)}
            for rule in rules
        )
        payload: dict[str, object] = {
            "status": "ok",
            "basis": basis,
            "profile": (
                {"version": str(profile.version), "content": asdict(profile.content)}
                if profile
                else None
            ),
            "profile_loaded": include_profile,
            "project": (
                {
                    "id": str(project.id),
                    "version": str(project.version),
                    "title": project.title,
                    "purpose": project.purpose,
                    "status": project.status,
                }
                if project
                else None
            ),
            "confirmed_rules": [serialize_memory(rule) for rule in rules],
        }
        encode_context(payload)
        return payload

    async def read_note(
        self, actor: ActorContext, *, session_id: str, memory_id: UUID
    ) -> dict[str, object]:
        session = await self.sessions.read(actor, session_id=session_id)
        memory = await self.memories.read(actor, memory_id)
        if memory.state == "retired" or (
            memory.project_id is not None and memory.project_id != session.project_id
        ):
            raise MemoryNotFound("Memory does not belong to the current work scope")
        payload: dict[str, object] = {"status": "ok", "memory": serialize_memory(memory)}
        encode_context(payload)
        return payload

    async def propose_rule(
        self, actor: ActorContext, *, session_id: str, title: str, content: str
    ) -> WorkspaceMemory:
        session = await self.sessions.read(actor, session_id=session_id)
        proposal_key = json.dumps(
            [actor.user_id, session_id, actor.request_id, title.strip(), content.strip()],
            ensure_ascii=False,
        )
        return await self.memories.create(
            actor,
            memory_id=uuid5(NAMESPACE_URL, proposal_key),
            project_id=session.project_id,
            kind="rule",
            title=title,
            content=content,
            source="职业伙伴提议",
        )

    async def read_material(
        self, actor: ActorContext, *, session_id: str, material_id: UUID
    ) -> dict[str, object]:
        if self.materials is None:
            raise MaterialNotFound("Materials are not available")
        session = await self.sessions.read(actor, session_id=session_id)
        detail = await self.materials.read(actor, material_id)
        if (
            detail.material.project_id is not None
            and detail.material.project_id != session.project_id
        ):
            raise MaterialNotFound("Material does not belong to the current work scope")
        payload: dict[str, object] = {
            "status": "ok",
            "material": {
                "id": str(detail.material.id),
                "title": detail.material.title,
                "project_id": str(detail.material.project_id)
                if detail.material.project_id
                else None,
                "current_version": str(detail.current_version.id),
                "version_number": detail.current_version.number,
                "body": detail.current_version.body,
                "pending_draft": next(
                    (
                        {
                            "id": str(item.id),
                            "base_version_id": str(item.base_version_id),
                            "body": item.proposed_body,
                            "rationale": item.rationale,
                            "status": "unconfirmed_expression",
                            "review_version": str(item.review_version),
                            "changes": list(item.changes),
                        }
                        for item in detail.proposals
                        if item.state == "pending"
                        and (item.review_version_id or item.base_version_id)
                        == detail.current_version.id
                    ),
                    None,
                ),
            },
        }
        encode_context(payload)
        return payload

    async def propose_material_edit(
        self,
        actor: ActorContext,
        *,
        session_id: str,
        material_id: UUID,
        base_version_id: UUID,
        proposed_body: str,
        rationale: str,
        references: tuple[dict[str, str], ...] = (),
        proposal_id: UUID | None = None,
        change_id: str | None = None,
        review_version: UUID | None = None,
    ) -> dict[str, object]:
        if self.materials is None:
            raise MaterialInvalid("Materials are not available")
        session = await self.sessions.read(actor, session_id=session_id)
        detail = await self.materials.read(actor, material_id)
        if (
            detail.material.project_id is not None
            and detail.material.project_id != session.project_id
        ):
            raise MaterialNotFound("Material does not belong to the current work scope")
        if proposal_id is not None:
            if (
                change_id is None
                or review_version is None
                or base_version_id != detail.current_version.id
            ):
                raise MaterialInvalid("Read the current material and select one pending change")
            reviewed = await self.materials.resolve(
                actor,
                material_id,
                proposal_id,
                state="accepted",
                change_ids=(change_id,),
                expected_version=review_version,
                replacement=proposed_body,
            )
            return {
                "status": "pending",
                "proposal_id": str(proposal_id),
                "material_id": str(material_id),
                "review_version": str(
                    next(
                        item.review_version for item in reviewed.proposals if item.id == proposal_id
                    )
                ),
                "message": "所选待审建议已改写，正文与其他决定未改变，仍需用户审阅。",
            }
        if change_id is not None or review_version is not None:
            raise MaterialInvalid("Select the proposal for a targeted rewrite")
        proposal = await self.materials.propose(
            actor,
            material_id,
            base_version_id=base_version_id,
            proposed_body=proposed_body,
            rationale=rationale,
            references=references,
        )
        payload: dict[str, object] = {
            "status": proposal.state,
            "message": "材料修改提议已保存，请在材料审阅中核对 Diff 后接受或拒绝。",
            "proposal": {
                "id": str(proposal.id),
                "material_id": str(proposal.material_id),
                "base_version_id": str(proposal.base_version_id),
                "rationale": proposal.rationale,
            },
        }
        encode_context(payload)
        return payload

    async def list_materials(
        self, actor: ActorContext, *, session_id: str, cursor: str | None = None
    ) -> dict[str, object]:
        if self.materials is None:
            raise MaterialNotFound("Materials are not available")
        session = await self.sessions.read(actor, session_id=session_id)
        page = await self.materials.list(
            actor, project_id=session.project_id, limit=20, cursor=cursor, scoped=True
        )
        payload: dict[str, object] = {
            "status": "ok",
            "next_cursor": page.next_cursor,
            "items": [
                {"id": str(item.id), "title": item.title, "version": str(item.current_version_id)}
                for item in page.items
            ],
        }
        encode_context(payload)
        return payload

    async def propose_new_material(
        self,
        actor: ActorContext,
        *,
        session_id: str,
        title: str,
        proposed_body: str,
        rationale: str,
        references: tuple[dict[str, str], ...],
    ) -> dict[str, object]:
        if self.materials is None:
            raise MaterialInvalid("Materials are not available")
        session = await self.sessions.read(actor, session_id=session_id)
        key = json.dumps(
            [actor.user_id, actor.request_id, title.strip(), proposed_body.strip()],
            ensure_ascii=False,
        )
        detail = await self.materials.create(
            actor,
            material_id=uuid5(NAMESPACE_URL, key),
            project_id=session.project_id,
            title=title,
            body="",
            draft=MaterialDraft(proposed_body.strip(), rationale.strip(), references),
        )
        return {
            "status": "pending",
            "material_id": str(detail.material.id),
            "title": detail.material.title,
            "message": "草稿已保存为待审阅提议。接受前没有已确认正文，请在资料与成果审阅。",
        }
