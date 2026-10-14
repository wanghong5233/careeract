from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from services.browser.sessions.authentication import BrowserCommand, CommandRejected


class PostgresMessagePermit:
    """Final single-use admission for a signed, domain-authorized message attempt.

    No decision or text is authored here. The existing domain ledger is the
    authority; consume before editor I/O so response loss cannot replay a write.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def consume(self, command: BrowserCommand) -> None:
        if command.action != "send_message" or command.owner_id != "boss-reply":
            raise CommandRejected("Not a message permit")
        async with self.engine.begin() as db:
            delegated = await db.scalar(
                text(
                    "SELECT automation_id FROM career.communication_sends WHERE task_id=:task "
                    "AND user_id=:user"
                ),
                {"task": command.task_id, "user": command.sub},
            )
            if delegated is not None:
                allowed = await db.scalar(
                    text(
                        "SELECT 1 FROM career.recruiting_automations "
                        "WHERE id=:id AND user_id=:user "
                        "AND status='running' AND expires_at>clock_timestamp() FOR SHARE"
                    ),
                    {"id": delegated, "user": command.sub},
                )
                if not allowed:
                    raise CommandRejected("Reply delegation was stopped or expired")
            await db.execute(
                text(
                    "SELECT c.id FROM career.boss_connections c JOIN career.execution_resources r "
                    "ON r.connection_id=c.id AND r.user_id=c.user_id WHERE r.task_id=:task "
                    "FOR SHARE OF c"
                ),
                {"task": command.task_id},
            )
            payload = (
                (
                    await db.execute(
                        text(
                            "SELECT s.text,s.source,p.message_id,p.decision,x.request_id "
                            "FROM career.communication_sends s "
                            "JOIN career.communication_replies p ON p.id=s.reply_id "
                            "JOIN career.execution_attempts x ON x.task_id=s.task_id "
                            "WHERE s.task_id=:task AND s.user_id=:user"
                        ),
                        {"task": command.task_id, "user": command.sub},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if payload is None:
                raise CommandRejected("Message payload unavailable")
            human = [
                m
                for m in payload["source"]["payload"]["messages"]
                if m["sender"] in {"candidate", "recruiter"}
            ]
            if (
                payload["decision"] is None
                or payload["decision"].get("category") != "routine"
                or payload["decision"].get("text") != payload["text"]
                or not payload["decision"].get("facts")
                or any(
                    fact.get("field") in {"goals", "constraints"}
                    for fact in payload["decision"].get("facts", [])
                )
                or not human
                or human[-1]["sender"] != "recruiter"
                or payload["message_id"] != command.message_id
                or payload["request_id"] != command.request_id
                or sha256(payload["text"].encode()).hexdigest() != command.text_digest
                or sha256(human[-1]["content"].encode()).hexdigest() != command.source_digest
            ):
                raise CommandRejected("Message payload binding changed")
            allowed = await db.scalar(
                text(
                    "UPDATE career.execution_attempts x SET outcome='send_attempted',"
                    "updated_at=clock_timestamp() FROM career.execution_authorizations a,"
                    "career.execution_resources r,career.boss_connections c "
                    "WHERE x.id=:attempt AND x.task_id=:task AND x.user_id=:user "
                    "AND x.authorization_id=:authorization AND x.browser_session_id=:session "
                    "AND x.status='running' AND x.outcome='send_preparing' "
                    "AND a.id=x.authorization_id AND a.status='active' "
                    "AND a.scope='boss.reply' AND a.expires_at>clock_timestamp() "
                    "AND r.task_id=x.task_id AND r.conversation_id=:conversation "
                    "AND c.id=r.connection_id AND c.user_id=x.user_id "
                    "AND c.status='connected' AND c.version=r.connection_version RETURNING x.id"
                ),
                {
                    "attempt": command.attempt_id,
                    "task": command.task_id,
                    "user": command.sub,
                    "authorization": command.authorization_id,
                    "session": command.session_id,
                    "conversation": command.conversation_id,
                },
            )
            if not allowed:
                raise CommandRejected("Message attempt already consumed or revoked")
