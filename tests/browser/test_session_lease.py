from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from services.browser.sessions.lease import LeaseConflict, SessionLeaseStore

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_owner_renews_only_with_matching_lease_identity() -> None:
    store = SessionLeaseStore()
    session_id = uuid4()
    lease = store.acquire(session_id, "agent:1", ttl=timedelta(seconds=30), now=NOW)

    renewed = store.renew(
        session_id,
        lease.lease_id,
        "agent:1",
        ttl=timedelta(seconds=30),
        now=NOW + timedelta(seconds=10),
    )

    assert renewed.lease_id == lease.lease_id
    assert renewed.expires_at == NOW + timedelta(seconds=40)


def test_other_writer_cannot_acquire_renew_or_release_active_lease() -> None:
    store = SessionLeaseStore()
    session_id = uuid4()
    lease = store.acquire(session_id, "playwright", ttl=timedelta(seconds=30), now=NOW)

    with pytest.raises(LeaseConflict):
        store.acquire(session_id, "human", ttl=timedelta(seconds=30), now=NOW)
    with pytest.raises(LeaseConflict):
        store.renew(
            session_id,
            lease.lease_id,
            "human",
            ttl=timedelta(seconds=30),
            now=NOW,
        )
    with pytest.raises(LeaseConflict):
        store.release(session_id, lease.lease_id, "human", writer_stopped=True)


def test_expiry_blocks_writes_and_does_not_allow_automatic_takeover() -> None:
    store = SessionLeaseStore()
    session_id = uuid4()
    old = store.acquire(session_id, "browser-use", ttl=timedelta(seconds=5), now=NOW)

    expired = NOW + timedelta(seconds=5)
    assert store.current(session_id) == old
    with pytest.raises(LeaseConflict):
        store.acquire(session_id, "human", ttl=timedelta(seconds=30), now=expired)
    with pytest.raises(LeaseConflict):
        store.require_writer(session_id, old.lease_id, "browser-use", now=expired)
    with pytest.raises(LeaseConflict):
        store.renew(
            session_id,
            old.lease_id,
            "browser-use",
            ttl=timedelta(seconds=30),
            now=NOW + timedelta(seconds=5),
        )


def test_handoff_waits_for_disconnection_and_rejects_stale_executor() -> None:
    store = SessionLeaseStore()
    session_id = uuid4()
    old = store.acquire(session_id, "playwright", ttl=timedelta(seconds=30), now=NOW)
    with pytest.raises(LeaseConflict):
        store.release(session_id, old.lease_id, "playwright", writer_stopped=True)
    store.stop_writes(session_id, old.lease_id, "playwright")
    with pytest.raises(LeaseConflict):
        store.require_writer(session_id, old.lease_id, "playwright", now=NOW)
    with pytest.raises(LeaseConflict):
        store.renew(session_id, old.lease_id, "playwright", ttl=timedelta(seconds=30), now=NOW)
    with pytest.raises(LeaseConflict):
        store.release(session_id, old.lease_id, "playwright", writer_stopped=False)
    store.release(session_id, old.lease_id, "playwright", writer_stopped=True)
    new = store.acquire(session_id, "human", ttl=timedelta(seconds=30), now=NOW)
    assert new.lease_id != old.lease_id
    with pytest.raises(LeaseConflict):
        store.release(session_id, old.lease_id, "playwright", writer_stopped=True)
    assert store.require_writer(session_id, new.lease_id, "human", now=NOW) == new


def test_same_owner_cannot_bypass_token_by_acquiring_again() -> None:
    store = SessionLeaseStore()
    session_id = uuid4()
    store.acquire(session_id, "human", ttl=timedelta(seconds=30), now=NOW)
    with pytest.raises(LeaseConflict):
        store.acquire(session_id, "human", ttl=timedelta(seconds=30), now=NOW)


def test_concurrent_writers_have_only_one_winner() -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    store = SessionLeaseStore()
    session_id = uuid4()
    barrier = Barrier(3)

    def acquire(owner: str) -> bool:
        barrier.wait(timeout=5)
        try:
            store.acquire(session_id, owner, ttl=timedelta(seconds=30), now=NOW)
            return True
        except LeaseConflict:
            return False

    with ThreadPoolExecutor(max_workers=3) as executor:
        assert sum(executor.map(acquire, ["playwright", "browser-use", "human"])) == 1
