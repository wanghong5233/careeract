from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.openai import OpenAIChat
from agno.os import AgentOS
from agno.os.interfaces.agui import AGUI
from sqlalchemy import create_engine

from services.api.app.settings import Settings
from services.api.infrastructure.agent_tools import PARTNER_INSTRUCTIONS


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
        cache_callables=False,
        instructions=PARTNER_INSTRUCTIONS,
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
