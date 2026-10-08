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
60-second lifetime. Issue time tolerates at most two seconds of clock skew between
services; expiration remains strict and the signed lifetime may not exceed 60 seconds.
It binds the user, session, task, authorization, executor,
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

The API's internal `BrowserRegistrationService` now persists real login task,
authorization, and attempt records (migration `0020_execution_semantics`) and reserves
a session ID before using this register command. Its scope is only `boss.login`,
with a maximum 15-minute authorization. The product Viewer issuer checks these
records and the exact registered session, caps its ticket by the stored authorization
deadline, and uses the real attempt ID. A standalone registration with arbitrary
task/authorization UUIDs no longer qualifies for a product Viewer ticket.

Registration confirms only the ownership registry, not Steel creation or login.
Lost responses and interrupted attempts survive reconstruction and block resending.
Revocation first disables the domain authorization, then sends the signed Browser
Service revoke command; started attempts retain `cleanup_required` and writer leases
remain until trusted disconnect is confirmed. Product connection POST/GET/DELETE,
the Web login card, and the same-origin Viewer proxy now call these application use
cases. Physical lifecycle wiring is described below.

## Signed physical lifecycle

`POST /internal/v1/sessions/{id}/lifecycle/{create|release}` accepts dedicated
EdDSA commands with no client body. It checks registered ownership, current command
time and absence of any writer lease. Release also requires prior revocation.
Command consumption commits before external I/O; a second transaction locks the
session through Steel mutation and readback, excluding acquisition and revocation
while the physical operation is in flight. The existing persistent Steel reservation
blocks reconstruction or a fresh token from replaying uncertain operations.

`BrowserRegistrationService.create` reserves creation in the domain database before
calling the route. Revision `0021_browser_lifecycle` adds creation/release outcomes;
confirmed creation associates the connection with the exact session and enters
`waiting_for_login`, which still does not prove a page has loaded or login succeeded.
Lost responses, interrupted creation and concurrent domain revocation retain evidence
and require cleanup/reconciliation. Viewer tickets now require `browser_created`,
the exact connection/session relationship and a `live` Steel reservation.

`release` first disables domain authorization and sends Browser revocation, then
requests physical release. It waits up to seven seconds for a revoked human Viewer
to confirm disconnection; automatic or uncertain writer leases still block it. Only trusted
disconnect confirmation can clear the lease. Confirmed physical release records
`browser_released` and revokes the connection. This does not delete encrypted
snapshots, platform credentials, disk profiles or backups. Product HTTP orchestration
is wired, while automatic cleanup and deployment configuration remain pending.

The API optionally configures `BROWSER_BASE_URL` and its private command key to
construct the existing internal control client. Browser Service constructs the
manager from its configured Steel client/database. Missing configuration keeps the
internal lifecycle unavailable. The signed ASGI route is verified against isolated
PostgreSQL and the pinned real Steel create/release path, plus synthetic failure and
concurrency cases; it has not been verified in a deployed product login flow.

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

## Steel lifecycle adapter

`steel.py` manages create/inspect/release against the pinned Steel OSS instance.
It is a trusted internal adapter, not an HTTP execution or product login endpoint.
The caller must check ownership and consent, and stop/disconnect all executors and
Viewer channels before calling release. A lifecycle reservation is not a writer lease.

The pinned image's release controller ignores the path session ID; its per-ID GET
also fabricates a released result for unknown IDs. The adapter reads the session
inventory instead, refuses unowned or mismatched sessions, and verifies mutation
responses and subsequent inventory. It returns only ID/status, discarding debug,
CDP, cookie, and page data. It follows no redirects and retries no mutations.

Revision `0018_steel_operations` reserves the single instance in PostgreSQL before
each side effect. All managers use the same database and one configured Steel
instance; advisory locking and a partial unique index coordinate reservations.
`creating`/`releasing` survive cancellation, unknown responses, and process restart.
They block further creation/release; inspection never clears them. Confirmed
release permits a new ID, while replaying an old release cannot close a new session.
Automated reconciliation of uncertain operations is not implemented; never delete
the reservation or infer completion from an absent inventory entry. Direct Steel
clients bypass this guard and must remain unavailable to product users.

## Encrypted context snapshots

`context.py` validates live Playwright `storage_state()` snapshots, keeping cookies
only for explicit cookie domains and localStorage only for exact HTTPS origins.
It rejects empty, oversized, malformed, ambiguous, and partitioned-cookie state.
Only cookies/localStorage are supported; IndexedDB, sessionStorage, service workers,
and filesystem Profile directories are not captured. No storage values are logged.

`SteelSessionManager.export_context` requires an owned live lifecycle reservation and
checks inventory before and after the snapshot. Its trusted caller must supply the
Playwright context connected to that session and hold an exclusive executor lease,
with all human Viewer channels disconnected. The lifecycle lock serializes creation
and release, but is not an executor lease or proof of caller identity. These adapters
are not yet exposed by HTTP or bound to product connection requests.

The pinned Steel native export merges disk and live-page localStorage using different
keys; it can include stale disk values and loses the live origin scheme. Production
snapshot export therefore uses Playwright's live canonical origins. Restore still
uses Steel's native `sessionContext` during reserved creation, without copying disk
directories or changing vendor code. Import is never automatically retried.

`profiles.py` stores authenticated AES-256-GCM ciphertext in `browser.profiles`
(migration `0019_browser_profiles`). A dedicated 32-byte raw key file can be loaded
through `ProfileCipher.from_file`; no production key configuration is wired yet.
Ciphertext binds the user, site, profile ID, version, expiry, scope, and format version.
Reads and version-conditional saves are scoped to the user/site; retention is at most
30 days and saves do not extend it. Expired records require explicit revocation before
new creation. Revocation clears the live row's ciphertext and retains a tombstone,
preventing stale saves from resurrecting it. A new login gets a new profile ID.

Revoking this snapshot alone does not stop a running browser, invalidate a platform
session, erase backups, or clear Steel disk files. Product forgetting requires the
signed session to be revoked and physically released. Only snapshots saved before
that release are cleared; a newer login rejects the old removal command. Automatic
expiry cleanup, key rotation, and disk cleanup remain separate work. The
real Steel canary uses synthetic `example.com` state and isolated PostgreSQL; it
proves encrypted snapshot restore after adapter/connection reconstruction and a clean
next session, not a BOSS login or browser process restart.

## Viewer boundary

`viewer.py` is the first half of the same-origin takeover boundary. It accepts only
the configured Steel cast WebSocket endpoint, rewrites it to a CareerAct-relative
path carrying the server-selected session ID, rejects other WebSocket/devtools URLs,
limits the HTML size, and requires an exact Origin. It does not create a ticket,
authorize a user, proxy a WebSocket, or expose a product route by itself. The
Browser Service now has an internal `GET /internal/v1/sessions/{session_id}/viewer`
route that accepts a short-lived signed `viewer` command, rechecks the registered
session, fetches Steel debug HTML without redirects, and returns only rewritten
HTML with `no-store` and same-origin frame policy. It is still not a product route:
the API can now issue the matching 60-second command only for an existing, unrevoked
registered session, and the internal cast route proxies text/binary WebSocket frames
to Steel after rechecking that cookie. The cast connection acquires the existing durable
writer lease, consumes its ticket, and excludes automatic executors and other Viewers.
It checks authorization before forwarding input and renews the lease every five seconds;
expiry, revocation, draining, or unavailable coordination stops the relay. Trusted cleanup
marks it draining and releases ownership only after the upstream WebSocket has closed.
Uncertain connection or disconnect outcomes retain ownership for reconciliation.
Caddy and Next forward only the exact cast path. Viewer HTML and renewal go through
the authenticated Web BFF and API. The pinned Steel single-page interactive template
is selected after checking the active inventory and page ownership; discovery and
extra cast parameters are rejected to preserve one exclusive writer channel.

The Viewer calls same-origin renewal every 20 seconds. The API rechecks the persisted
login task, authorization, attempt, connection and live reservation, then sends a fresh
60-second signed command to `POST /internal/v1/sessions/{id}/viewer/renew`. Browser
Service requires the existing channel with matching identity/scope and lease, consumes
the new command, and renews without extending the original login authorization. A
process-local channel registry only locates the running relay; PostgreSQL remains the
lease authority. Process restart cannot revive an unknown lease. Failed renewal stops
the UI and the relay expires within its existing signed deadline. Reopening after a
confirmed disconnect obtains a new ticket through the authenticated HTML route.

Local product create/release, same-origin single-page cast and renewal beyond one
minute have been verified. The compatibility image also passes manual BOSS login,
encrypted Cookie/localStorage saving and repeated product-session restore.
Explicit login completion verifies account and message navigation before saving,
physical release and the product connection update. This authorizes no messaging.

The pinned implementation uses shared Profile paths and does not honor arbitrary
`userDataDir` as an isolated directory. Real BOSS snapshots are retained encrypted
in PostgreSQL with a separate local key. Clean sequential session storage has canary
evidence, but disk cleanup, production isolation and long-term login validity still
require separate verification.
