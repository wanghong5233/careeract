# Routes

CareerAct REST and AG-UI endpoints live here.

- Product REST endpoints use `/api/v1`.
- `/agui` is reserved for the AG-UI stream and is reached through the Web BFF.
- Domain failures use `{ "error": { "code": "...", "message": "...", "request_id": "..." } }`.
- Collection endpoints use cursor pagination; they do not expose database offsets.
- Mutable resources expose an opaque version and reject stale writes.
- Externally visible write operations require an idempotency key, except operations
  whose external result is uncertain; those stop for reconciliation instead of retrying.
- Routes translate transport types and call application use cases. They do not query
  databases or call infrastructure adapters directly.

`GET/POST /api/v1/connections/boss` reads or records a user-owned BOSS connection
request. POST requires a UUID `Idempotency-Key` and an empty JSON object. Same-key
replay returns the original record, including a revoked record; a different key
while a request is active returns 409. `DELETE /api/v1/connections/boss/{id}` requires
JSON `{version}`, preserves the revoked record and is idempotent after revocation.
Cross-user IDs return 404; stale versions or an attached browser session return 409.
These use cases only persist `pending`/`revoked`, create no browser session and do
not authorize platform access or messaging. Future browser-backed revocation must
stop the trusted executor and verify disconnection before claiming completion.

`GET/POST/DELETE /api/v1/connections/boss/{id}/login` manages the short-lived,
explicitly authorized `boss.login` execution. It creates or reads the durable task,
authorization and attempt; it does not accept credentials. The browser Viewer is
available at `GET /api/v1/browser/sessions/{session_id}/viewer` only after confirmed
physical creation and returns same-origin HTML with a short-lived HttpOnly cookie.

`GET /api/v1/profile` reads the authenticated user's singleton confirmed profile;
an absent profile returns empty content and a null version. `PUT /api/v1/profile`
requires content, explicit confirmation and the version returned by the last read.
It performs a conditional replacement in one transaction, without external side effects
or automatic retries. A stale version or racing first creation returns 409. The owner
cannot be supplied in JSON; no endpoint accepts another user's profile ID. Only the
current version is retained. Version history and Agent access are separate work.

`GET /api/v1/projects` lists the authenticated user's projects with an opaque cursor;
`POST /api/v1/projects` creates a planned project; `GET /api/v1/projects/{id}` and
`PATCH /api/v1/projects/{id}` read or conditionally update one project. The owner is
always taken from the verified token, never from the request body. Updates require the
current `version`; another user's ID is indistinguishable from not found, and stale
writes return 409. Project milestones, tasks and Agent context are separate work.

`DELETE /api/v1/projects/{id}` requires the current `version` in JSON and returns
204 after a conditional deletion. Missing or other-owned projects return 404; stale
versions return 409. In the same transaction, project notes/rules are retired with a
new version before their association is cleared, so project rules never become global
rules. Materials and Agent sessions remain user-owned with their project association
cleared. This deletes the project organization, not all personal data or runtime copies.

`PUT /api/v1/agent/session` associates the authenticated user's opaque Agent session
with an optional CareerAct project. The session ID is derived by the Web BFF and is
never treated as a user-supplied owner. `GET /api/v1/agent/session/history?session_id=...`
first checks that association, then returns only the current user's `user`/`assistant`
text messages from the Agent runtime. Framework history, tool messages, and another
user's session are not exposed; session history is treated as career data and responses
are not cached.

History now separates the final assistant response from its optional `process`:
public progress messages and safe tool labels/status/duration projected from the
same Agno Run. No raw reasoning, system messages, tool arguments or results are
returned. Missing final text retains the actual Run status and saved process.
The projection and privacy boundaries are defined in the
[runtime topic](../../../docs/topics/agent-runtime/README.md#运行过程展示边界).

`DELETE /api/v1/agent/conversations/{session_id}` requires JSON `{version}` and
returns 200 `{status: "deleted"}` only after framework deletion is verified and
the directory row is removed. Other-owned/missing conversations return 404;
stale versions, active/unreconciled Runs or open related side chats return 409.
Unconfirmed framework deletion returns 503 and must be reconciled before retrying.
Temporary side sessions use their existing close endpoint. Retention and
cross-connection limitations are defined in the
[runtime topic](../../../docs/topics/agent-runtime/README.md#对话删除).

`POST /api/v1/agent/side-chats` creates one temporary, user-owned side session from
an exact saved assistant message and optional quote; the source project and context
version are fixed at creation. `POST /api/v1/agent/side-chats/{session_id}/close`
discards a side session only after its Agno Run is terminal, removes the temporary
runtime session and product directory row, and is idempotent for an already missing
row. Side sessions are excluded from the regular conversation directory, survive
refresh, and are eligible for bounded server cleanup after 24 hours. They do not
create a second message store or a persistent conversation-management surface.

`POST /api/v1/agent/conversations/{session_id}/branch` creates a regular independent
conversation from a saved message boundary. `before` branches retain terminal
exchanges before the latest edited user message; `after` branches retain that completed
assistant answer and prior exchanges. The source directory and any material or
external side effects remain unchanged; active or non-terminal source Runs are
rejected. The framework Session is copied only through the bounded adapter, rather
than exposing a general-purpose rollback tree.

`/api/v1/memories` stores user-owned notes and rule candidates. A new item is always
`candidate`; only an explicit `POST /api/v1/memories/{id}/confirm` with the current
version can make a rule effective. `POST /api/v1/memories/{id}/retire` removes an item
from default reads while retaining the soft-retired row. Updates are conditional on the
opaque version; editing a confirmed rule returns it to `candidate` until it is explicitly
confirmed again. All reads/writes are scoped to the verified user.
Project associations are checked against that same user inside the write transaction.
A client can supply a stable create ID; replay requires identical title, content, kind,
source and project, and a retired or mismatched record returns 409. Notes stay unconfirmed
and cannot use the rule-confirmation endpoint. Only the current text and soft-retired row
are retained; this is not a revision audit log. Agent access is separate work.

`/api/v1/materials` is a default-disabled synthetic text experiment, enabled only
with `SYNTHETIC_MATERIALS_ENABLED=true`. Lists use cursors; each material has an
immutable version history and proposals tied to an exact base version. Agent-created
materials begin with an empty seed and a pending draft, never an accepted body.
Accepting a proposal atomically writes a new version and resolves it; replay does not
apply it twice. A stale proposal cannot be accepted but can be rejected. Its original
Diff and source versions remain available. User edits require the current version.
Agent tools can list, read and propose within the authenticated session/project scope;
they cannot accept or reject. Model-produced expression does not confirm profile facts
or authorize an external application. No file upload or real private-data import is open.
