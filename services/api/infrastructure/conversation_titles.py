import asyncio

from agno.agent import Agent
from agno.exceptions import ModelProviderError
from agno.models.message import Message
from agno.models.openai import OpenAIChat
from agno.run.agent import RunOutput
from agno.session.agent import AgentSession

from services.api.app.settings import Settings
from services.api.domain.work_session import WorkSessionUnavailable


class AgnoConversationTitleGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, prompt: str) -> str:
        settings = self.settings
        agent = Agent(
            model=OpenAIChat(
                id=settings.litellm_model,
                api_key=settings.litellm_api_key.get_secret_value(),
                base_url=str(settings.litellm_base_url),
                timeout=3,
                max_retries=0,
                max_tokens=64,
            ),
            telemetry=False,
        )
        session = AgentSession(
            session_id="title-only",
            runs=[RunOutput(messages=[Message(role="user", content=prompt)])],
        )
        try:
            title = await asyncio.wait_for(
                asyncio.to_thread(agent.generate_session_name, session), timeout=12
            )
        except (ModelProviderError, TimeoutError):
            raise WorkSessionUnavailable("Conversation naming is unavailable") from None
        if not isinstance(title, str) or title == "New Session":
            raise WorkSessionUnavailable("Conversation naming returned no title")
        return title
