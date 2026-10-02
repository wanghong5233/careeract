import json
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from agno.run.base import RunContext

from services.api.application.context import ActorContext
from services.api.domain.memory import MemoryInvalid, MemoryUnavailable
from services.api.domain.privacy import RestrictedContent, ensure_career_content
from services.api.domain.profile import ProfileUnavailable
from services.api.domain.project import ProjectNotFound, ProjectUnavailable
from services.api.domain.work_session import WorkSessionNotFound, WorkSessionUnavailable

MAX_CONTEXT_CHARS = 12_000


def _actor(run_context: RunContext) -> ActorContext:
    if not run_context.user_id:
        raise ValueError("Authenticated user is required")
    return ActorContext(user_id=run_context.user_id, request_id=run_context.run_id)


def _compact_profile(profile: Any) -> dict[str, Any]:
    content = asdict(profile.content)
    return {
        "version": str(profile.version),
        "confirmed_at": profile.confirmed_at.isoformat(),
        "content": content,
    }


def _compact_memory(memory: Any) -> dict[str, Any]:
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


def _safe_json(value: dict[str, Any]) -> str:
    ensure_career_content(value)
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > MAX_CONTEXT_CHARS:
        return json.dumps(
            {
                "status": "truncated",
                "message": "上下文超出本次读取上限；请按具体对象继续询问。",
            },
            ensure_ascii=False,
        )
    return encoded


def build_agent_tools(
    profile_service: Any,
    project_service: Any,
    memory_service: Any,
    work_session_service: Any,
) -> Callable[..., list[Callable[..., Any]]]:
    def tools(*, run_context: RunContext) -> list[Callable[..., Any]]:
        async def read_career_context() -> str:
            """Read the user's confirmed career context and current project.

            Use this before answering a question that depends on the user's background,
            goals, constraints, or confirmed working rules. Notes are marked unverified.
            The server derives the user and project from the authenticated run.
            """

            actor = _actor(run_context)
            try:
                profile = await profile_service.read(actor)
                session = await work_session_service.read(actor, session_id=run_context.session_id)
                project = None
                if session.project_id is not None:
                    project = await project_service.read(actor, session.project_id)
                rules = await memory_service.list(
                    actor,
                    cursor=None,
                    limit=25,
                    kind="rule",
                    include_retired=False,
                )
                notes = await memory_service.list(
                    actor,
                    cursor=None,
                    limit=10,
                    kind="note",
                    include_retired=False,
                )
            except (ProfileUnavailable, ProjectUnavailable, ProjectNotFound):
                return json.dumps(
                    {
                        "status": "unavailable",
                        "message": "职业上下文暂时无法读取，请稍后重试。",
                    },
                    ensure_ascii=False,
                )
            except (MemoryUnavailable, WorkSessionUnavailable, WorkSessionNotFound):
                return json.dumps(
                    {
                        "status": "unavailable",
                        "message": "长期上下文暂时无法读取，请稍后重试。",
                    },
                    ensure_ascii=False,
                )

            payload: dict[str, Any] = {
                "status": "ok",
                "basis": [],
                "profile": _compact_profile(profile) if profile else None,
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
                "confirmed_rules": [
                    _compact_memory(item) for item in rules.items if item.state == "confirmed"
                ],
                "unverified_notes": [_compact_memory(item) for item in notes.items],
            }
            if profile:
                payload["basis"].append({"type": "profile", "version": str(profile.version)})
            if project:
                payload["basis"].append(
                    {"type": "project", "id": str(project.id), "version": str(project.version)}
                )
            payload["basis"].extend(
                {"type": "memory", "id": item["id"], "version": item["version"]}
                for item in payload["confirmed_rules"] + payload["unverified_notes"]
            )
            return _safe_json(payload)

        async def propose_career_rule(title: str, content: str) -> str:
            """Save a candidate rule for the user to review and explicitly confirm.

            This never confirms, retires, or changes an effective rule. Do not include
            identity numbers, passwords, one-time codes, cookies, or access tokens.
            """

            actor = _actor(run_context)
            try:
                session = await work_session_service.read(actor, session_id=run_context.session_id)
                candidate = await memory_service.create(
                    actor,
                    memory_id=None,
                    project_id=session.project_id,
                    kind="rule",
                    title=title,
                    content=content,
                    source="职业伙伴提议",
                )
            except (MemoryInvalid, RestrictedContent):
                return json.dumps(
                    {
                        "status": "rejected",
                        "message": "规则提议未保存，请移除受限信息并提供有效内容。",
                    },
                    ensure_ascii=False,
                )
            except (MemoryUnavailable, WorkSessionUnavailable, WorkSessionNotFound):
                return json.dumps(
                    {
                        "status": "unavailable",
                        "message": "规则提议暂时无法保存，请稍后重试。",
                    },
                    ensure_ascii=False,
                )
            return _safe_json(
                {
                    "status": "candidate",
                    "message": "已保存为待确认规则；用户确认前不会影响后续工作。",
                    "memory": _compact_memory(candidate),
                }
            )

        return [read_career_context, propose_career_rule]

    return tools
