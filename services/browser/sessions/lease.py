from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import UUID, uuid4


class LeaseConflict(Exception):
    pass


class LeaseNotFound(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SessionLease:
    session_id: UUID
    lease_id: UUID
    owner_id: str
    expires_at: datetime
    draining: bool = False

    def is_active(self, now: datetime) -> bool:
        return not self.draining and now < self.expires_at


class SessionLeaseStore:
    """Process-local lease rules; production persistence is a separate adapter."""

    def __init__(self) -> None:
        self._leases: dict[UUID, SessionLease] = {}
        self._lock = Lock()

    def acquire(
        self,
        session_id: UUID,
        owner_id: str,
        *,
        ttl: timedelta,
        now: datetime | None = None,
    ) -> SessionLease:
        current_time = _utc_now() if now is None else _ensure_utc(now)
        if ttl <= timedelta(0):
            raise ValueError("Lease TTL must be positive")
        if not owner_id.strip():
            raise ValueError("Lease owner must not be empty")
        with self._lock:
            current = self._leases.get(session_id)
            if current is not None:
                raise LeaseConflict("Previous writer must be stopped before acquiring the session")
            lease = SessionLease(
                session_id=session_id,
                lease_id=uuid4(),
                owner_id=owner_id,
                expires_at=current_time + ttl,
            )
            self._leases[session_id] = lease
            return lease

    def renew(
        self,
        session_id: UUID,
        lease_id: UUID,
        owner_id: str,
        *,
        ttl: timedelta,
        now: datetime | None = None,
    ) -> SessionLease:
        current_time = _utc_now() if now is None else _ensure_utc(now)
        if ttl <= timedelta(0):
            raise ValueError("Lease TTL must be positive")
        with self._lock:
            current = self._require(session_id, lease_id, owner_id, current_time)
            return self._replace(current, current_time, ttl)

    def stop_writes(self, session_id: UUID, lease_id: UUID, owner_id: str) -> None:
        with self._lock:
            current = self._leases.get(session_id)
            if current is None:
                raise LeaseNotFound("Session lease not found")
            if current.lease_id != lease_id or current.owner_id != owner_id:
                raise LeaseConflict("Lease is owned by another writer")
            self._leases[session_id] = SessionLease(
                session_id=current.session_id,
                lease_id=current.lease_id,
                owner_id=current.owner_id,
                expires_at=current.expires_at,
                draining=True,
            )

    def release(
        self, session_id: UUID, lease_id: UUID, owner_id: str, *, writer_stopped: bool
    ) -> None:
        with self._lock:
            current = self._leases.get(session_id)
            if current is None:
                return
            if current.lease_id != lease_id or current.owner_id != owner_id:
                raise LeaseConflict("Lease is owned by another writer")
            if not current.draining or not writer_stopped:
                raise LeaseConflict("Stop writes and confirm executor disconnection before release")
            del self._leases[session_id]

    def current(self, session_id: UUID) -> SessionLease | None:
        with self._lock:
            return self._leases.get(session_id)

    def require_writer(
        self, session_id: UUID, lease_id: UUID, owner_id: str, *, now: datetime
    ) -> SessionLease:
        with self._lock:
            return self._require(session_id, lease_id, owner_id, _ensure_utc(now))

    def _require(
        self,
        session_id: UUID,
        lease_id: UUID,
        owner_id: str,
        now: datetime,
    ) -> SessionLease:
        current = self._leases.get(session_id)
        if current is None:
            raise LeaseNotFound("Session lease not found")
        if current.lease_id != lease_id or current.owner_id != owner_id:
            raise LeaseConflict("Lease is owned by another writer")
        if not current.is_active(now):
            raise LeaseConflict("Expired or draining lease cannot write or renew")
        return current

    def _replace(self, current: SessionLease, now: datetime, ttl: timedelta) -> SessionLease:
        renewed = SessionLease(
            session_id=current.session_id,
            lease_id=current.lease_id,
            owner_id=current.owner_id,
            expires_at=now + ttl,
        )
        self._leases[current.session_id] = renewed
        return renewed


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _ensure_utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("Lease timestamps must include timezone information")
    return value.astimezone(UTC)
