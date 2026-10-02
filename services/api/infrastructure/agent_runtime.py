from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.openai import OpenAIChat
from agno.os import AgentOS
from agno.os.interfaces.agui import AGUI
from sqlalchemy import create_engine

from services.api.app.settings import Settings


def build_agent_os(settings: Settings) -> AgentOS:
    db = PostgresDb(
        db_url=str(settings.agno_database_url),
        db_engine=create_engine(
            str(settings.agno_database_url),
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={"connect_timeout": 5},
        ),
        db_schema=settings.agno_database_schema,
    )
    career_agent = Agent(
        id="careeract-agent",
        name="CareerAct",
        model=OpenAIChat(
            id=settings.litellm_model,
            api_key=settings.litellm_api_key.get_secret_value(),
            base_url=str(settings.litellm_base_url),
        ),
        db=db,
        debug_mode=False,
        store_media=False,
        instructions=(
            "You are the user's CareerAct career partner. Help plan and create the next "
            "authorized career action. Before relying on personal background, goals, "
            "constraints, projects, or rules, call read_career_context. Treat notes as "
            "unverified and confirmed rules as the only effective constraints. When the "
            "user asks to retain a new working rule, use propose_career_rule; it creates "
            "a candidate for explicit user review and confirmation. Never claim a rule is "
            "effective until the user confirms it, and never request or repeat identity "
            "numbers, passwords, one-time codes, cookies, or access tokens. When a response "
            "used career context, end with a concise '本次依据' listing the returned object "
            "types and versions; do not expose internal reasoning or tool traces."
        ),
        telemetry=False,
    )
    return AgentOS(
        id="careeract",
        description="CareerAct domain backend and agent runtime",
        agents=[career_agent],
        interfaces=[AGUI(agent=career_agent)],
        db=db,
        telemetry=False,
        tracing=False,
    )
