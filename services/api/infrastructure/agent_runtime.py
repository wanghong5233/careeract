from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.openai import OpenAIChat
from agno.os import AgentOS
from agno.os.interfaces.agui import AGUI

from services.api.app.settings import Settings


def build_agent_os(settings: Settings) -> AgentOS:
    db = PostgresDb(
        db_url=str(settings.agno_database_url),
        db_schema=settings.agno_database_schema,
    )
    career_agent = Agent(
        id="careeract-agent",
        name="CareerAct",
        model=OpenAIChat(
            id=settings.litellm_model,
            api_key=settings.litellm_master_key.get_secret_value(),
            base_url=str(settings.litellm_base_url),
        ),
        db=db,
        instructions="Help the user plan their career and complete the next authorized action.",
        telemetry=False,
    )
    return AgentOS(
        id="careeract",
        description="CareerAct domain backend and agent runtime",
        agents=[career_agent],
        interfaces=[AGUI(agent=career_agent)],
        db=db,
        telemetry=False,
    )
