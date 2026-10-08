from uuid import uuid4

import pytest
from pydantic import AnyHttpUrl

from services.browser.sessions.viewer import (
    ViewerContext,
    ViewerRejected,
    cast_websocket_url,
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
