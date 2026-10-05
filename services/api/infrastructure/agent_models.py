import httpx
import yaml
from agno.agent import Agent
from agno.models.openai import OpenAIChat

from services.api.app.settings import Settings
from services.api.application.ports.agent_models import RuntimeModel
from services.api.domain.work_session import WorkSessionInvalid, WorkSessionUnavailable


class LiteLLMModelCatalog:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def list(self) -> tuple[RuntimeModel, ...]:
        try:
            config = yaml.safe_load(self.settings.litellm_config_path.read_text(encoding="utf-8"))
            async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                response = await client.get(
                    str(self.settings.litellm_base_url).rstrip("/") + "/v1/models",
                    headers={
                        "Authorization": "Bearer "
                        + self.settings.litellm_api_key.get_secret_value()
                    },
                )
                response.raise_for_status()
                allowed = {item["id"] for item in response.json()["data"]}
            result = []
            for item in config["model_list"]:
                if item["model_name"] not in allowed:
                    continue
                information = item.get("model_info", {})
                provider, _, model = item["litellm_params"]["model"].partition("/")
                result.append(
                    RuntimeModel(
                        item["model_name"],
                        information.get("provider", provider),
                        model,
                        information.get("display_name", model),
                    )
                )
            return tuple(result)
        except (OSError, yaml.YAMLError, httpx.HTTPError, ValueError, KeyError, TypeError):
            raise WorkSessionUnavailable("Model configuration is unavailable") from None

    async def require(self, model_id: str) -> RuntimeModel:
        model = next((item for item in await self.list() if item.id == model_id), None)
        if model is None:
            raise WorkSessionInvalid("Model is not supported by this runtime")
        return model

    def agent_for(self, agent: Agent, model: RuntimeModel) -> Agent:
        return agent.deep_copy(
            update={
                "model": OpenAIChat(
                    id=model.id,
                    api_key=self.settings.litellm_api_key.get_secret_value(),
                    base_url=str(self.settings.litellm_base_url),
                )
            }
        )
