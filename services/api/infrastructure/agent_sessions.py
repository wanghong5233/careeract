from typing import Any

from agno.exceptions import AgnoError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from services.api.application.ports.work_sessions import AgentHistoryMessage
from services.api.domain.work_session import WorkSessionHistoryUnavailable


class AgnoAgentHistoryReader:
    def __init__(self, agent: Any) -> None:
        self.agent = agent

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
                limit=limit,
            )
        except (AgnoError, DBAPIError, PoolTimeoutError, ValueError, TypeError) as error:
            raise WorkSessionHistoryUnavailable("Agent history is unavailable") from error
        result: list[AgentHistoryMessage] = []
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
                )
            )
        return tuple(result[-limit:])
