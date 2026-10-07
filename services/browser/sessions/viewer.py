from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import UUID

import httpx
from pydantic import AnyHttpUrl

MAX_VIEWER_HTML_BYTES = 512 * 1024
MAX_VIEWER_PAGE_ID_BYTES = 256
CAST_PATH = "/v1/sessions/cast"


class ViewerRejected(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ViewerContext:
    session_id: UUID
    origin: str
    steel_origin: str


def validate_origin(context: ViewerContext, origin: str | None) -> None:
    if origin != context.origin:
        raise ViewerRejected("Viewer origin rejected")


def _validate_page_id(page_id: str) -> str:
    if not page_id or len(page_id.encode("utf-8")) > MAX_VIEWER_PAGE_ID_BYTES:
        raise ViewerRejected("Viewer page is invalid")
    if any(ord(character) < 0x20 for character in page_id):
        raise ViewerRejected("Viewer page is invalid")
    return page_id


async def fetch_viewer_document(
    client: httpx.AsyncClient, page_id: str, context: ViewerContext
) -> str:
    page_id = _validate_page_id(page_id)
    try:
        response = await client.get(
            "/v1/sessions/debug",
            params={"pageId": page_id},
            follow_redirects=False,
            timeout=20,
        )
    except httpx.TransportError:
        raise ViewerRejected("Viewer document unavailable") from None
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    content_length = response.headers.get("content-length")
    if (
        response.status_code != 200
        or content_type != "text/html"
        or (content_length is not None and not content_length.isdigit())
        or (content_length is not None and int(content_length) > MAX_VIEWER_HTML_BYTES)
    ):
        raise ViewerRejected("Viewer document unavailable")
    try:
        html = response.content.decode("utf-8")
    except UnicodeDecodeError:
        raise ViewerRejected("Viewer document is invalid") from None
    return rewrite_viewer_html(html, context)


def rewrite_viewer_html(html: str, context: ViewerContext) -> str:
    if len(html.encode("utf-8")) > MAX_VIEWER_HTML_BYTES:
        raise ViewerRejected("Viewer document is too large")
    if "javascript:" in html.lower():
        raise ViewerRejected("Viewer document contains an unsupported URL")
    rewritten = html
    found = False
    steel = urlsplit(context.steel_origin)
    for quote in ('"', "'"):
        start = 0
        while True:
            index = min(
                (
                    candidate
                    for candidate in (
                        rewritten.find("ws://", start),
                        rewritten.find("wss://", start),
                    )
                    if candidate >= 0
                ),
                default=-1,
            )
            if index < 0:
                break
            end = rewritten.find(quote, index)
            if end < 0:
                raise ViewerRejected("Viewer WebSocket URL is malformed")
            parsed = urlsplit(rewritten[index:end])
            if (
                parsed.hostname != steel.hostname
                or parsed.port != steel.port
                or parsed.path != CAST_PATH
            ):
                raise ViewerRejected("Viewer WebSocket URL is not a Steel cast endpoint")
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            query["sessionId"] = str(context.session_id)
            relative = f"/api/browser/sessions/{context.session_id}/cast"
            if query:
                relative += "?" + urlencode(query)
            rewritten = rewritten[:index] + relative + rewritten[end:]
            found = True
            start = index + len(relative)
    if not found:
        raise ViewerRejected("Viewer document has no Steel cast endpoint")
    if context.steel_origin in rewritten or "devtools" in rewritten.lower():
        raise ViewerRejected("Viewer document exposes an internal browser endpoint")
    return rewritten


def viewer_context(
    *, session_id: UUID, origin: AnyHttpUrl, steel_origin: AnyHttpUrl
) -> ViewerContext:
    return ViewerContext(
        session_id=session_id,
        origin=str(origin).rstrip("/"),
        steel_origin=str(steel_origin).rstrip("/"),
    )
