from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from agno.agent import Agent
from agno.models.openai import OpenAIChat

from services.api.domain.work_session import WorkSessionConflict, WorkSessionInvalid
from services.api.infrastructure.agent_models import LiteLLMModelCatalog
from tests.api.test_conversation_titles import title_fixture
from tests.api.test_health import build_settings


@pytest.mark.asyncio
async def test_catalog_intersects_gateway_permission_and_config_without_exposing_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = tmp_path / "models.yaml"
    configuration.write_text(
        "model_list:\n  - model_name: allowed\n"
        "    litellm_params: {model: openai/synthetic, api_key: synthetic-secret}\n"
        "    model_info: {provider: Synthetic, display_name: Synthetic Model}\n"
        "  - model_name: denied\n    litellm_params: {model: openai/other}\n",
        encoding="utf-8",
    )
    factory = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"data": [{"id": "allowed"}, {"id": "not-configured"}]})
    )
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: factory(transport=transport, **kwargs)
    )
    catalog = LiteLLMModelCatalog(
        build_settings().model_copy(update={"litellm_config_path": configuration})
    )
    models = await catalog.list()
    assert [(item.id, item.model, item.provider, item.label) for item in models] == [
        ("allowed", "synthetic", "Synthetic", "Synthetic Model")
    ]
    assert "secret" not in repr(models)
    with pytest.raises(WorkSessionInvalid):
        await catalog.require("denied")
    original = Agent(model=OpenAIChat(id="original"), telemetry=False, add_history_to_context=True)
    copied = catalog.agent_for(original, models[0])
    assert copied is not original and copied.model is not original.model
    assert copied.model.id == "allowed" and original.model.id == "original"
    assert copied.add_history_to_context


@pytest.mark.asyncio
async def test_active_run_and_unsupported_model_cannot_change_conversation() -> None:
    service, session, actor = title_fixture()
    history: Any = service.history
    history.has_active_run.return_value = True
    service.models = AsyncMock()
    changes: Any = dict(
        actor=actor,
        session_id=session.session_id,
        title=None,
        archived=None,
        project_id=None,
        change_project=False,
        expected_version=session.version,
        model_id="synthetic",
    )
    with pytest.raises(WorkSessionConflict):
        await service.update(**changes)
    repository: Any = service.repository
    repository.update.assert_not_awaited()
    history.has_active_run.return_value = False
    models: Any = service.models
    models.require.side_effect = WorkSessionInvalid("unsupported")
    with pytest.raises(WorkSessionInvalid):
        await service.update(**changes)
    repository.update.assert_not_awaited()
