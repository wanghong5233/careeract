import json
from unittest.mock import Mock

import pytest
from agno.run.base import RunContext
from ddgs.exceptions import TimeoutException

from services.api.infrastructure.agent_search import build_web_search


@pytest.mark.asyncio
async def test_public_search_reuses_provider_and_returns_unverified_bounded_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Mock(
        return_value=json.dumps(
            [
                {
                    "title": "Synthetic source",
                    "href": "https://example.com",
                    "body": "Synthetic snippet",
                },
                {"href": "javascript:invalid"},
            ]
        )
    )
    provider.__name__ = "web_search"
    monkeypatch.setattr(
        "services.api.infrastructure.agent_search.WebSearchTools.web_search", provider
    )
    search = build_web_search(
        RunContext(run_id="synthetic", session_id="synthetic", user_id="synthetic")
    )
    result = json.loads(await search("Public synthetic information"))
    assert result == {
        "status": "found",
        "sources": [
            {
                "title": "Synthetic source",
                "url": "https://example.com",
                "snippet": "Synthetic snippet",
            }
        ],
        "verified": False,
    }
    assert provider.call_args.args == ("Public synthetic information",)
    await search("second")
    await search("third")
    assert json.loads(await search("fourth"))["status"] == "rejected"
    assert provider.call_count == 3


@pytest.mark.asyncio
async def test_search_distinguishes_empty_failure_and_rejection_without_query_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Mock(side_effect=["[]", TimeoutException("Synthetic provider detail")])
    provider.__name__ = "web_search"
    monkeypatch.setattr(
        "services.api.infrastructure.agent_search.WebSearchTools.web_search", provider
    )
    search = build_web_search(
        RunContext(run_id="synthetic", session_id="synthetic", user_id="synthetic")
    )
    assert json.loads(await search(""))["status"] == "rejected"
    assert json.loads(await search("x" * 301))["status"] == "rejected"
    assert json.loads(await search("password: synthetic-private-value"))["status"] == "rejected"
    assert provider.call_count == 0
    assert json.loads(await search("Public empty query"))["status"] == "empty"
    failed = await search("Public failure query")
    assert json.loads(failed)["status"] == "unavailable"
    assert "Synthetic provider detail" not in failed
    assert provider.call_count == 2
