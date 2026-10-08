import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import httpx
from pydantic import AnyHttpUrl, BaseModel, ValidationError

MAX_VIEWER_HTML_BYTES = 512 * 1024
MAX_VIEWER_PAGE_ID_BYTES = 256
CAST_PATH = "/v1/sessions/cast"
VIEWER_COOKIE_PREFIX = "careeract_viewer_"


class ViewerRejected(Exception):
    pass


class _SteelSession(BaseModel):
    id: UUID
    status: str


class _SteelInventory(BaseModel):
    sessions: list[_SteelSession]


class _SteelPage(BaseModel):
    id: str


class _SteelPages(BaseModel):
    pages: list[_SteelPage]


async def resolve_viewer_page(
    client: httpx.AsyncClient, session_id: UUID, page_id: str | None
) -> str:
    page_id = validate_page_id(page_id)
    try:
        inventory = await client.get("/v1/sessions", follow_redirects=False, timeout=10)
        if inventory.status_code != 200:
            raise ViewerRejected("Viewer session unavailable")
        sessions = _SteelInventory.model_validate_json(inventory.content).sessions
        active = [session for session in sessions if session.status in {"live", "idle"}]
        if len(active) != 1 or active[0].id != session_id or active[0].status != "live":
            raise ViewerRejected("Viewer session unavailable")
        details = await client.get(
            f"/v1/sessions/{session_id}/live-details", follow_redirects=False, timeout=10
        )
        if details.status_code != 200:
            raise ViewerRejected("Viewer page unavailable")
        pages = _SteelPages.model_validate_json(details.content).pages
    except (httpx.TransportError, ValidationError):
        raise ViewerRejected("Viewer page unavailable") from None
    identifiers = [validate_page_id(page.id) for page in pages]
    if len(set(identifiers)) != len(identifiers):
        raise ViewerRejected("Viewer pages are ambiguous")
    if page_id is None:
        if len(identifiers) != 1:
            raise ViewerRejected("Viewer requires one selected page")
        page_id = identifiers[0]
    if page_id is None or page_id not in identifiers:
        raise ViewerRejected("Viewer page unavailable")
    return page_id


@dataclass(frozen=True, slots=True)
class ViewerContext:
    session_id: UUID
    origin: str
    steel_origin: str


def validate_origin(context: ViewerContext, origin: str | None) -> None:
    if origin != context.origin:
        raise ViewerRejected("Viewer origin rejected")


def _validate_page_id(page_id: str | None) -> str | None:
    if page_id is None:
        return None
    if not page_id or len(page_id.encode("utf-8")) > MAX_VIEWER_PAGE_ID_BYTES:
        raise ViewerRejected("Viewer page is invalid")
    if any(ord(character) < 0x20 for character in page_id):
        raise ViewerRejected("Viewer page is invalid")
    return page_id


def validate_page_id(page_id: str | None) -> str | None:
    return _validate_page_id(page_id)


def viewer_cookie_name(session_id: UUID) -> str:
    return VIEWER_COOKIE_PREFIX + session_id.hex


def cast_websocket_url(
    context: ViewerContext, page_id: str | None, query: Mapping[str, str] | None = None
) -> str:
    page_id = _validate_page_id(page_id)
    steel = urlsplit(context.steel_origin)
    parameters = dict(query or {})
    if page_id is not None:
        parameters["pageId"] = page_id
    parameters["sessionId"] = str(context.session_id)
    query_string = urlencode(parameters)
    scheme = "wss" if steel.scheme == "https" else "ws"
    return urlunsplit((scheme, steel.netloc, CAST_PATH, query_string, ""))


async def fetch_viewer_document(
    client: httpx.AsyncClient, page_id: str | None, context: ViewerContext
) -> str:
    page_id = _validate_page_id(page_id)
    try:
        response = await client.get(
            "/v1/sessions/debug",
            params={
                key: value
                for key, value in {"pageId": page_id, "interactive": "true"}.items()
                if value is not None
            },
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
    rewritten = rewrite_viewer_html(html, context)
    renewal = """<script>
(() => {
    let stopped = false;
    let pending = false;
    const timer = setInterval(async () => {
        if (stopped || pending) return;
        pending = true;
        try {
            const response = await fetch('__RENEW_PATH__', {
                method: 'POST', credentials: 'same-origin', cache: 'no-store',
                signal: AbortSignal.timeout(8000)
            });
            if (!response.ok) throw new Error('Viewer renewal stopped');
        } catch {
            stopped = true;
            clearInterval(timer);
            const notice = document.createElement('div');
            notice.setAttribute('role', 'status');
            notice.textContent = '登录浏览器已断开，请返回招聘沟通页面重新读取状态。';
            Object.assign(notice.style, {
                position: 'fixed', inset: '0', zIndex: '9999', background: '#fff',
                color: '#111', display: 'grid', placeItems: 'center', padding: '24px'
            });
            document.body.appendChild(notice);
        } finally {
            pending = false;
        }
    }, 20000);
    window.addEventListener('pagehide', () => { stopped = true; clearInterval(timer); });
})();
</script>""".replace("__RENEW_PATH__", f"/api/browser/sessions/{context.session_id}/viewer-renew")
    return rewritten + renewal


def rewrite_viewer_html(html: str, context: ViewerContext) -> str:
    if len(html.encode("utf-8")) > MAX_VIEWER_HTML_BYTES:
        raise ViewerRejected("Viewer document is too large")
    if "javascript:" in html.lower():
        raise ViewerRejected("Viewer document contains an unsupported URL")
    found = False
    steel = urlsplit(context.steel_origin)

    def replace_endpoint(match: re.Match[str]) -> str:
        nonlocal found
        parsed = urlsplit(match.group("url"))
        if (
            parsed.hostname != steel.hostname
            or parsed.port != steel.port
            or parsed.path != CAST_PATH
        ):
            raise ViewerRejected("Viewer WebSocket URL is not a Steel cast endpoint")
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        relative = f"/api/browser/sessions/{context.session_id}/cast"
        if query:
            query["sessionId"] = str(context.session_id)
            relative += "?" + urlencode(query)
        found = True
        return match.group("quote") + relative + match.group("quote")

    rewritten = re.sub(
        r"(?P<quote>['\"])(?P<url>wss?://[^'\"\s]+)(?P=quote)", replace_endpoint, html
    )
    if "ws://" in rewritten or "wss://" in rewritten:
        raise ViewerRejected("Viewer WebSocket URL is malformed")
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
