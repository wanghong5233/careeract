from uuid import uuid4

import httpx
import pytest
from pydantic import AnyHttpUrl

from services.browser.sessions.viewer import (
    ViewerContext,
    ViewerRejected,
    cast_websocket_url,
    resolve_viewer_page,
    rewrite_viewer_html,
    validate_origin,
    viewer_context,
)


def context() -> ViewerContext:
    return viewer_context(
        session_id=uuid4(),
        origin=AnyHttpUrl("https://careeract.example"),
        steel_origin=AnyHttpUrl("http://steel:3000"),
    )


def test_rewrites_only_the_configured_steel_cast_endpoint() -> None:
    current = context()
    html = '<script>const ws="ws://steel:3000/v1/sessions/cast?pageId=page-a"</script>'
    rewritten = rewrite_viewer_html(html, current)
    assert f"/api/browser/sessions/{current.session_id}/cast" in rewritten
    assert "pageId=page-a" in rewritten
    assert "sessionId=" + str(current.session_id) in rewritten
    assert "steel:3000" not in rewritten


def test_cast_url_preserves_multi_page_discovery_without_exposing_steel() -> None:
    current = context()
    url = cast_websocket_url(current, None, {"tabInfo": "true"})
    assert url.endswith("/v1/sessions/cast?tabInfo=true&sessionId=" + str(current.session_id))


def test_rewrites_single_quoted_base_endpoint_without_duplicate_query_separator() -> None:
    current = context()
    html = "<script>const baseWsUrl = 'ws://steel:3000/v1/sessions/cast';</script>"
    rewritten = rewrite_viewer_html(html, current)
    assert f"'{f'/api/browser/sessions/{current.session_id}/cast'}'" in rewritten
    assert "?" not in rewritten


@pytest.mark.parametrize(
    "html",
    [
        '<script>const ws="ws://other:3000/v1/sessions/cast"</script>',
        '<script>const ws="ws://steel:3000/devtools"</script>',
        "<script>const ws = 'ws://steel:3000/v1/sessions/cast</script>",
        "<script>location='javascript:alert(1)'</script>",
        "<html>no websocket</html>",
    ],
)
def test_rejects_untrusted_or_incomplete_viewer_documents(html: str) -> None:
    with pytest.raises(ViewerRejected):
        rewrite_viewer_html(html, context())


def test_rejects_oversized_viewer_document() -> None:
    with pytest.raises(ViewerRejected):
        rewrite_viewer_html(
            '<script>const ws="ws://steel:3000/v1/sessions/cast"</script>' + ("x" * (512 * 1024)),
            context(),
        )


def test_origin_is_exact_and_never_wildcard() -> None:
    current = context()
    validate_origin(current, "https://careeract.example")
    with pytest.raises(ViewerRejected):
        validate_origin(current, "https://evil.example")
    with pytest.raises(ViewerRejected):
        validate_origin(current, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("pages", "requested", "accepted"),
    [
        (["page-a"], None, "page-a"),
        (["page-a", "page-b"], "page-b", "page-b"),
        ([], None, None),
        (["page-a", "page-b"], None, None),
        (["page-a"], "unowned-page", None),
        (["page-a", "page-a"], "page-a", None),
        ([""], None, None),
    ],
)
async def test_page_selection_requires_owned_unambiguous_target(
    pages: list[str], requested: str | None, accepted: str | None
) -> None:
    current = context()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/sessions":
            return httpx.Response(
                200, json={"sessions": [{"id": str(current.session_id), "status": "live"}]}
            )
        assert request.url.path == f"/v1/sessions/{current.session_id}/live-details"
        return httpx.Response(200, json={"pages": [{"id": page} for page in pages]})

    async with httpx.AsyncClient(
        base_url=current.steel_origin, transport=httpx.MockTransport(handler)
    ) as client:
        if accepted is None:
            with pytest.raises(ViewerRejected):
                await resolve_viewer_page(client, current.session_id, requested)
        else:
            assert await resolve_viewer_page(client, current.session_id, requested) == accepted


@pytest.mark.asyncio
async def test_page_selection_rejects_steel_inventory_for_another_session() -> None:
    current = context()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/sessions"
        return httpx.Response(200, json={"sessions": [{"id": str(uuid4()), "status": "live"}]})

    async with httpx.AsyncClient(
        base_url=current.steel_origin, transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ViewerRejected):
            await resolve_viewer_page(client, current.session_id, None)
