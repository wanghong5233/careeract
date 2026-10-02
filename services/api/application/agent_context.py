import json
from dataclasses import asdict
from uuid import NAMESPACE_URL, UUID, uuid5

from services.api.application.context import ActorContext
from services.api.application.memories import MemoryService
from services.api.application.profiles import ProfileService
from services.api.application.projects import ProjectService
from services.api.application.work_sessions import AgentWorkSessionService
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
    ) -> None:
        self.profiles, self.projects = profiles, projects
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
