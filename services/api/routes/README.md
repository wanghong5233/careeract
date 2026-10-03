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
