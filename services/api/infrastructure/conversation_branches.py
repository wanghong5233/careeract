import asyncio
import json
import time
from typing import Any
from uuid import UUID, uuid4, uuid5

from agno.agent._init import has_async_db
from agno.exceptions import AgnoError
from agno.models.message import Message
from agno.run.agent import RunOutput
from agno.session.agent import AgentSession
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from services.api.application.context import ActorContext
from services.api.application.work_sessions import AgentWorkSessionService
from services.api.domain.work_session import (
    AgentWorkSession,
    WorkSessionConflict,
    WorkSessionHistoryUnavailable,
    WorkSessionInvalid,
)
from services.api.infrastructure.agent_execution import lock_conversation
from services.api.infrastructure.work_sessions import work_session_from_row


def bounded_branch_runs(
    source: AgentSession,
    message_id: str,
    mode: str,
    scope: str,
    target_id: str,
    target_scope: str,
    identifier: UUID,
) -> list[RunOutput]:
    result: list[RunOutput] = []
    found = False
    for run in source.runs or []:
        if getattr(run, "parent_run_id", None) is not None:
            continue
        messages: list[Message] = []
        selected = False
        for message in run.messages or []:
            if message.from_history:
                continue
            if message.id == message_id:
                if (mode == "before" and message.role != "user") or (
                    mode == "after" and (message.role != "assistant" or message.tool_calls)
                ):
                    raise WorkSessionInvalid("Invalid saved message boundary")
                selected = True
                if mode == "before":
                    break
            if message.role in {"user", "assistant"} and not message.tool_calls:
                content = message.get_content_string()
                if content:
                    messages.append(
                        Message(
                            id=message.id,
                            role=message.role,
                            content=content,
                            created_at=message.created_at,
                        )
                    )
            if selected:
                break
        if selected:
            found = True
            if (run.metadata or {}).get("career_scope") != scope:
                raise WorkSessionConflict("The selected boundary belongs to a different scope")
            if mode == "before":
                break
        if (run.metadata or {}).get("career_scope") == scope and messages:
            status = str(getattr(run.status, "value", run.status))
            if status not in {"COMPLETED", "CANCELLED", "ERROR", "REGENERATED"}:
                raise WorkSessionConflict("Reconcile non-terminal runs before branching")
            if selected and mode == "after" and status != "COMPLETED":
                raise WorkSessionInvalid("Select a completed answer")
            result.append(
                RunOutput(
                    run_id=str(uuid5(identifier, run.run_id)),
                    session_id=target_id,
                    agent_id=source.agent_id,
                    user_id=source.user_id,
                    status=run.status,
                    messages=messages,
                    content=messages[-1].get_content_string()
                    if messages[-1].role == "assistant"
                    else None,
                    metadata={
                        "career_scope": target_scope,
                        "branch_source_run": run.run_id,
                        **(
                            {"career_interrupted": True}
                            if (run.metadata or {}).get("career_interrupted")
                            else {}
                        ),
                    },
                    created_at=run.created_at,
                    forked_from_session_id=source.session_id,
                )
            )
        if selected:
            break
    if not found:
        raise WorkSessionInvalid("Select a saved message in the current conversation")
    return result


class AgnoConversationBranches:
    def __init__(self, engine: AsyncEngine, sessions: AgentWorkSessionService, agent: Any) -> None:
        self.engine, self.sessions, self.agent = engine, sessions, agent

    async def create(
        self,
        actor: ActorContext,
        *,
        source_id: str,
        identifier: UUID,
        message_id: str,
        mode: str,
        title: str,
        expected_version: UUID,
    ) -> AgentWorkSession:
        title = self.sessions.validate_title(title)
        source = await self.sessions.read(actor, session_id=source_id)
        if source.temporary_until is not None or source.archived or mode not in {"before", "after"}:
            raise WorkSessionInvalid("Select an active regular conversation")
        target_id = f"conversation:{identifier}"
        context = {
            "source_id": source_id,
            "message_id": message_id,
            "mode": mode,
            "source_scope": str(source.context_version),
            "title": title,
        }
        try:
            async with self.engine.begin() as connection:
                await lock_conversation(connection, source_id)
                await lock_conversation(connection, target_id)
                existing = await self.sessions.repository.get(actor, target_id)
                if existing is not None:
                    if existing.branch_context != context:
                        raise WorkSessionConflict(
                            "Branch retry does not match the original request"
                        )
                    return existing
                occupied = await connection.scalar(
                    text("SELECT 1 FROM career.agent_work_sessions WHERE session_id=:id"),
                    {"id": target_id},
                )
                if occupied:
                    raise WorkSessionConflict("Branch ID is already in use")
                current = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM career.agent_work_sessions WHERE session_id=:id "
                                "AND user_id=:user FOR UPDATE"
                            ),
                            {"id": source_id, "user": actor.user_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if (
                    current is None
                    or current["version"] != expected_version
                    or current["version"] != source.version
                    or current["archived"]
                ):
                    raise WorkSessionConflict("Source conversation changed")
                if self.sessions.history and await self.sessions.history.has_active_run(
                    session_id=source_id, user_id=actor.user_id
                ):
                    raise WorkSessionConflict("Wait for the active run to end")
                source_session = await self.agent.aget_session(
                    session_id=source_id, user_id=actor.user_id
                )
                if source_session is None:
                    raise WorkSessionInvalid("Select a saved message")
                if mode == "before":
                    latest_user = next(
                        (
                            message.id
                            for run in reversed(source_session.runs or [])
                            if (run.metadata or {}).get("career_scope")
                            == str(source.context_version)
                            and getattr(run, "parent_run_id", None) is None
                            for message in reversed(run.messages or [])
                            if message.role == "user" and not message.from_history
                        ),
                        None,
                    )
                    if latest_user != message_id:
                        raise WorkSessionInvalid("Only the latest saved input can be edited")
                previous_session = await self.agent.aget_session(session_id=target_id)
                if previous_session is not None and (
                    previous_session.user_id != actor.user_id
                    or (previous_session.session_data or {}).get("branch_request") != context
                ):
                    raise WorkSessionConflict("Framework branch ID is already in use")
                scope = uuid4()
                runs = bounded_branch_runs(
                    source_session,
                    message_id,
                    mode,
                    str(source.context_version),
                    target_id,
                    str(scope),
                    identifier,
                )
                session = AgentSession(
                    session_id=target_id,
                    agent_id=self.agent.id,
                    user_id=actor.user_id,
                    session_data={"forked_from_session_id": source_id, "branch_request": context},
                    runs=runs,
                    created_at=int(time.time()),
                    updated_at=int(time.time()),
                )
                await self.save(session)
                row = (
                    (
                        await connection.execute(
                            text(
                                "INSERT INTO career.agent_work_sessions "
                                "(session_id,user_id,title,title_origin,project_id,model_id,context_version,"
                                "branch_context) VALUES (:id,:user,:title,'manual',:project,"
                                ":model,:scope,CAST(:context AS jsonb)) "
                                "ON CONFLICT DO NOTHING RETURNING *"
                            ),
                            {
                                "id": target_id,
                                "user": actor.user_id,
                                "title": title,
                                "project": source.project_id,
                                "model": source.model_id,
                                "scope": scope,
                                "context": json.dumps(context),
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise WorkSessionConflict("Branch ID is already in use")
                return work_session_from_row(row)
        except (AgnoError, DBAPIError, PoolTimeoutError, ValueError, TypeError):
            raise WorkSessionHistoryUnavailable(
                "Branch history could not be safely saved"
            ) from None

    async def save(self, session: AgentSession) -> None:
        database = self.agent.db
        if database is None:
            raise WorkSessionHistoryUnavailable("Framework storage is unavailable")
        if has_async_db(self.agent):
            saved = await database.upsert_session(session=session)
            for index, run in enumerate(session.runs or []):
                await database.upsert_run(
                    run=run, session_id=session.session_id, user_id=session.user_id, run_index=index
                )
        else:
            saved = await asyncio.to_thread(database.upsert_session, session=session)
            for index, run in enumerate(session.runs or []):
                await asyncio.to_thread(
                    database.upsert_run,
                    run=run,
                    session_id=session.session_id,
                    user_id=session.user_id,
                    run_index=index,
                )
        recovered = await self.agent.aget_session(
            session_id=session.session_id, user_id=session.user_id
        )
        if (
            saved is None
            or recovered is None
            or len(recovered.runs or []) != len(session.runs or [])
        ):
            raise WorkSessionHistoryUnavailable("Branch storage result is unconfirmed")
