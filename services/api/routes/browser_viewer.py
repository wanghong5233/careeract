from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict

from services.api.application.context import ActorContext
from services.api.application.ports.browser_viewer import (
    BrowserViewerTicket,
    BrowserViewerTicketIssuer,
)

router = APIRouter(prefix="/api/v1/browser/sessions", tags=["browser"])


class ViewerTicketResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    token: str
    expires_at: str


def get_issuer(request: Request) -> BrowserViewerTicketIssuer:
    issuer = getattr(request.app.state, "browser_viewer_ticket_issuer", None)
    if issuer is None:
        raise HTTPException(503, "Browser viewer is not configured")
    return cast(BrowserViewerTicketIssuer, issuer)


def get_actor(request: Request) -> ActorContext:
    request_id = str(uuid4())
    request.state.request_id = request_id
    return ActorContext(user_id=request.state.user_id, request_id=request_id)


def serialize(ticket: BrowserViewerTicket) -> ViewerTicketResponse:
    return ViewerTicketResponse(
        session_id=ticket.session_id,
        token=ticket.token,
        expires_at=ticket.expires_at.isoformat(),
    )


@router.get("/{session_id}/viewer")
async def viewer_document(
    session_id: UUID,
    issuer: Annotated[BrowserViewerTicketIssuer, Depends(get_issuer)],
    actor: Annotated[ActorContext, Depends(get_actor)],
    page_id: Annotated[str | None, Query(alias="pageId")] = None,
) -> Response:
    document = await issuer.document(actor, session_id, page_id)
    headers = {"Cache-Control": "no-store"}
    if document.set_cookie is not None:
        headers["Set-Cookie"] = document.set_cookie
    return Response(content=document.content, media_type=document.content_type, headers=headers)


@router.post("/{session_id}/viewer-ticket", response_model=ViewerTicketResponse)
async def issue_viewer_ticket(
    session_id: UUID,
    response: Response,
    issuer: Annotated[BrowserViewerTicketIssuer, Depends(get_issuer)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ViewerTicketResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize(await issuer.issue(actor, session_id))


@router.post("/{session_id}/viewer-renew", status_code=204)
async def renew_viewer_ticket(
    session_id: UUID,
    response: Response,
    issuer: Annotated[BrowserViewerTicketIssuer, Depends(get_issuer)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> None:
    response.headers["Cache-Control"] = "no-store"
    await issuer.renew(actor, session_id)
