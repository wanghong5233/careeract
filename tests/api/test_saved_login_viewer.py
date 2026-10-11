from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, call
from uuid import uuid4

import pytest

from services.api.application.boss_saved_login_viewer import BossSavedLoginViewerService
from services.api.application.context import ActorContext
from services.api.application.ports.browser_control import (
    BrowserControlContext,
    BrowserControlUncertain,
)
from services.api.domain.boss_saved_login_viewer import (
    BossSavedLoginViewer,
    SavedLoginViewerUnavailable,
)
from services.api.routes.boss_connections import serialize_saved_login_viewer


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_expired_viewer_stays_available_for_cleanup_before_reopening(
    cleanup_fails: bool,
) -> None:
    actor = ActorContext(user_id="viewer-user", request_id=str(uuid4()))
    now = datetime.now(UTC)
    old = BossSavedLoginViewer(
        uuid4(),
        actor.user_id,
        uuid4(),
        uuid4(),
        uuid4(),
        "live",
        now - timedelta(seconds=1),
        now,
        now,
    )
    fresh = replace(
        old, id=uuid4(), browser_session_id=uuid4(), expires_at=now + timedelta(minutes=30)
    )
    expired_context = BrowserControlContext(
        actor.user_id,
        old.browser_session_id,
        old.id,
        old.id,
        old.expires_at,
        old.id,
        uuid4(),
        "saved-login-viewer",
    )
    fresh_context = replace(
        expired_context,
        session_id=fresh.browser_session_id,
        task_id=fresh.id,
        authorization_id=fresh.id,
        attempt_id=fresh.id,
        authorization_expires_at=fresh.expires_at,
    )
    repository, control = AsyncMock(), AsyncMock()
    repository.read.return_value = old
    repository.begin_close.return_value = expired_context
    repository.reserve.return_value = fresh
    repository.context.return_value = fresh_context
    repository.mark_live.return_value = fresh
    service = BossSavedLoginViewerService(repository, control)
    result = await service.read(actor, old.connection_id)
    assert result is not None
    assert serialize_saved_login_viewer(result).expired is True
    assert result.status == "live"
    assert serialize_saved_login_viewer(fresh).expired is False
    control.send.assert_not_awaited()
    if cleanup_fails:
        control.lifecycle.side_effect = BrowserControlUncertain()
        with pytest.raises(SavedLoginViewerUnavailable):
            await service.open(actor, old.connection_id, expected_connection_version=old.version)
        repository.reserve.assert_not_awaited()
        repository.mark_released.assert_not_awaited()
    else:
        assert (
            await service.open(actor, old.connection_id, expected_connection_version=old.version)
            == fresh
        )
        assert control.mock_calls == [
            call.send(expired_context, "revoke"),
            call.lifecycle(expired_context, "release"),
            call.send(fresh_context, "register"),
            call.lifecycle(fresh_context, "create"),
        ]
        repository.mark_released.assert_awaited_once_with(actor, old.id)
