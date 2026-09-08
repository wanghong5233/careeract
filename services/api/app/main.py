from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.openai import OpenAIChat
from agno.os import AgentOS
from agno.os.interfaces.agui import AGUI
from fastapi.middleware.cors import CORSMiddleware

from services.api.app.settings import settings

db = PostgresDb(db_url=str(settings.agno_database_url))
career_agent = Agent(
    id="careeract-agent",
    name="CareerAct",
    model=OpenAIChat(
        id=settings.litellm_model,
        api_key=settings.litellm_master_key,
        base_url=settings.litellm_base_url,
    ),
    db=db,
    instructions="Help the user plan their career and complete the next authorized action.",
)
agent_os = AgentOS(
    id="careeract",
    description="CareerAct domain backend and agent runtime",
    agents=[career_agent],
    interfaces=[AGUI(agent=career_agent)],
    db=db,
)
app = agent_os.get_app()
app.state.settings = settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def health() -> dict[str, str]:
    return {"status": "ok"}


app.add_api_route("/health", health, methods=["GET"])
