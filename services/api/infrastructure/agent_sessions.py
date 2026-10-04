from typing import Any

from agno.exceptions import AgnoError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from services.api.application.ports.work_sessions import AgentContextBasis, AgentHistoryMessage
from services.api.domain.privacy import ensure_career_content
from services.api.domain.work_session import WorkSessionHistoryUnavailable


class AgnoAgentHistoryReader:
    def __init__(self, agent: Any) -> None:
        self.agent = agent

    async def runs(self, *, session_id: str, user_id: str) -> list[dict[str, str | None]]:
        try:
            session = await self.agent.aget_session(session_id=session_id, user_id=user_id)
        except (AgnoError, DBAPIError, PoolTimeoutError, ValueError, TypeError):
            raise WorkSessionHistoryUnavailable("Agent run status is unavailable") from None
        return (
            [
                {
                    "run_id": run.run_id,
                    "status": getattr(getattr(run, "status", None), "value", "UNKNOWN"),
                }
                for run in (session.runs or [])
                if getattr(run, "parent_run_id", None) is None
            ][-100:]
            if session
            else []
        )

    async def has_active_run(self, *, session_id: str, user_id: str) -> bool:
        try:
            session = await self.agent.aget_session(session_id=session_id, user_id=user_id)
        except (AgnoError, DBAPIError, PoolTimeoutError, ValueError, TypeError):
            raise WorkSessionHistoryUnavailable("Agent run status is unavailable") from None
        return bool(
            session
            and any(
                str(
                    getattr(
                        getattr(run, "status", None), "value", getattr(run, "status", "UNKNOWN")
                    )
                )
                not in {"COMPLETED", "CANCELLED", "ERROR", "REGENERATED"}
                for run in session.runs or []
            )
        )

    async def basis(self, *, session_id: str, user_id: str) -> AgentContextBasis:
        try:
            session = await self.agent.aget_session(session_id=session_id, user_id=user_id)
        except (AgnoError, DBAPIError, PoolTimeoutError, ValueError, TypeError):
            raise WorkSessionHistoryUnavailable("Agent context is unavailable") from None
        if session is None or not session.runs:
            return AgentContextBasis(run_id=None)
        latest = session.runs[-1]
        metadata = latest.metadata or {}
        references = self.safe_references(metadata.get("career_basis", []))
        proposals = self.safe_references(metadata.get("career_proposals", []))
        return AgentContextBasis(latest.run_id, references, proposals)

    @staticmethod
    def safe_references(value: object) -> tuple[dict[str, str], ...]:
        if not isinstance(value, list) or len(value) > 110:
            raise WorkSessionHistoryUnavailable("Invalid agent context references")
        result: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                raise WorkSessionHistoryUnavailable("Invalid agent context reference")
            reference = {
                key: child
                for key, child in item.items()
                if key in {"type", "id", "title", "version"} and isinstance(child, str)
            }
            ensure_career_content(reference)
            result.append(reference)
        return tuple(result)

    async def read(
        self, *, session_id: str, user_id: str, limit: int
    ) -> tuple[AgentHistoryMessage, ...]:
        try:
            session = await self.agent.aget_session(session_id=session_id, user_id=user_id)
            if session is None:
                return ()
            messages = session.get_messages(
                skip_roles=["system", "tool"],
                skip_history_messages=True,
                skip_statuses=[],
                limit=limit,
            )
        except (AgnoError, DBAPIError, PoolTimeoutError, ValueError, TypeError) as error:
            raise WorkSessionHistoryUnavailable("Agent history is unavailable") from error
        result: list[AgentHistoryMessage] = []
        message_runs = {
            message.id: (
                run.run_id,
                str(
                    getattr(
                        getattr(run, "status", None), "value", getattr(run, "status", "UNKNOWN")
                    )
                ),
            )
            for run in session.runs or []
            if getattr(run, "parent_run_id", None) is None
            for message in getattr(run, "messages", None) or []
        }
        for message in messages:
            if message.role not in {"user", "assistant"}:
                continue
            content = message.get_content_string()
            if not content:
                continue
            result.append(
                AgentHistoryMessage(
                    id=message.id,
                    role=message.role,
                    content=content,
                    created_at=message.created_at,
                    run_id=message_runs.get(message.id, (None, "UNKNOWN"))[0],
                    run_status=message_runs.get(message.id, (None, "UNKNOWN"))[1],
                )
            )
        return tuple(result[-limit:])
