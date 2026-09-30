# Sessions

Steel profiles, session leases, and human takeover coordination live here.

`lease.py` is a process-local policy prototype, not production coordination or an
authorization boundary. It is not wired to HTTP routes or Steel execution.

- Acquisition is exclusive, even for the same owner. Renewals require the lease ID.
- Expiry rejects writes and renewal but retains ownership. Time passing does not
  prove an in-flight browser operation has stopped.
- Handoff first marks the lease draining, denying subsequent writes and renewals.
  Release requires confirmation that the old executor has disconnected. Failed or
  uncertain disconnection keeps the session unavailable.
- `writer_stopped` is a trusted adapter assertion, never a value accepted from a
  client request. It proves neither the outcome of an application submission nor
  permission to retry that submission.
- A new owner gets a new lease ID. Stale executors cannot renew or release it.

Durable coordination is implemented in `postgres.py`, described below. Before exposing
execution, also enforce ownership at the connection/execution boundary. Checking a lease
and then separately sending CDP commands is not atomic. Restarting the process-local
prototype loses state and must never authorize reuse of a surviving Steel session.

Acceptance gates: [browser release checks](../../../docs/handbook/DEVELOPMENT.md#浏览器开放前检查).

## Persistent control boundary

`postgres.py` persists registered session ownership and lease state in the `browser`
schema (Alembic revision `0002_browser_sessions`). Each mutation locks the session
row in a transaction. Expiry uses database time; leases last at most 30 seconds and
cannot outlive the signed command. Expired ownership remains until trusted cleanup.
Successful mutation command IDs are consumed in the same transaction; replay is
rejected even after release. Records currently have no automatic retention cleanup.

`authentication.py` accepts only EdDSA commands signed by the configured API public
key, for issuer `careeract-api` and audience `careeract-browser`, with a maximum
60-second lifetime. It binds the user, session, task, authorization, executor,
attempt, action and lease ID. These keys are separate from Better Auth login keys.
The private signing key remains in the API. The API signing/HTTP adapter exists,
but no public authorization or task use case is wired to it yet.

The internal HTTP entry is `POST /internal/v1/sessions/{session_id}/lease/{action}`,
with a Bearer command and no identity or authorization fields accepted from a body.
Actions are `acquire`, `renew`, `stop` and `check`. `stop` only denies further writes;
it does not prove that an executor has disconnected. A successful `check` is an
instantaneous state check, not a permit to send CDP commands after releasing the lock.

Registration and revocation use separately scoped signed commands through
`POST /internal/v1/sessions/{session_id}/{register|revoke}`. They do not accept
unsigned ownership fields. Registration cannot rebind or reactivate an existing
session. Revocation of a not-yet-registered session writes a tombstone so a delayed
registration cannot resurrect it. Concurrent registration/revocation leaves it revoked.

`confirm_stopped` remains a trusted adapter method, never an HTTP operation.
It must only be called after stopping the actual executor. Lifecycle callbacks are
tested with Steel below, but no production executor registry is wired to these routes.
Revocation denies further commands and retains the old lease for cleanup; the control
route alone cannot yet disconnect a live browser.

The API adapter is `services/api/infrastructure/browser_control.py`. It consumes a
trusted `BrowserControlContext` after the caller checks current authorization and
session/task ownership. The context is not proof of consent and must not be created
directly from client JSON. Commands expire within 60 seconds and cannot outlive the
provided authorization expiry, except revocation, which must remain possible for cleanup.
No automatic retries or redirects are followed. Missing, malformed, mismatched or
expired responses raise an uncertain-result error for reconciliation. An uncertain
acquisition does not expose the unknown lease ID; automatic reconciliation is not yet
implemented, so callers must not issue another acquisition as a retry.

## Executor lifecycle

`execution.py` serializes trusted executor operations in one process. Stop disables
new operations immediately, persists draining, waits for the current operation,
disconnects, and only then invokes trusted release. Stop timeout does not cancel an
in-flight operation and does not release ownership. A failed or cancelled operation,
failed disconnect, or uncertain release blocks further use until reconciliation.
Stopping during a lease check prevents that not-yet-started operation while allowing cleanup.

These callbacks are wired to PostgreSQL and a real Playwright CDP connection in the
Steel integration test. They are not yet wired to a production executor registry or
Viewer proxy. The lock is process-local; it does not fence a second process that has
copied a lease or a raw CDP URL. Closing a Playwright connection invalidates its old
page handles, but does not prevent a new connection using a known raw URL. No public
browser operation route is exposed until the connection boundary is enforced.

Process-local locks are not used by the persistent adapter. Database state survives
process exit; startup does not clear or recycle surviving leases. Internal routes
return 503 when unconfigured. The health endpoint remains a liveness check only.
