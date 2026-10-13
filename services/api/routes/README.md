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
POST may also recover a connected login using its current version and a fresh request key.
Recovery preserves encrypted login and prior tasks, rejects active saved viewers or unfinished
read tasks, and binds a new current login task. Superseded login commands and keys return 409;
the new task must still pass login verification and physical release before becoming connected.

`POST /api/v1/connections/boss/{id}/read` accepts a bounded `boss.read` task with
JSON `{version, authorize_read: true, conversation_id?, human_control?}` and a UUID `Idempotency-Key`. It validates
the owned connected resource and its current version, atomically persists the task,
authorization and attempt, and returns 201. Authorization expires within 15 minutes
of database acceptance; replay retains the original task, deadline and cancellation.
Acceptance does not start a browser or read HR data. The bounded read includes initial
navigation to the fixed BOSS conversation page during guarded session creation;
an optional stable conversation ID binds the task and signed command to one conversation.
Opening that uniquely verified row uses an exclusive executor lease and may mark messages
read. Same-key requests with a different target conflict; refresh restores the saved
result without navigation or replay. Currently loaded messages are not all history.
login and messaging permissions remain separate. The authenticated Web BFF is connected.
`GET /api/v1/connections/boss/{id}/read/{task_id}` reads that task;
`DELETE` cancels an unstarted task and revokes its authorization, preserving history.
For a started task, DELETE persists a stop request and revokes read authorization; the
browser session is revoked and released before the task becomes `cancelled`. Until
physical release is confirmed it remains `waiting` and can be reconciled after refresh
or a process interruption. Cancellation replays safely and never reruns the read.
Missing, other-owned or differently bound task IDs return the same 404 error envelope.
These responses use `Cache-Control: no-store`.

`human_control: true` requires a selected conversation and explicit user intent. After a
successful initial read and confirmed executor disconnection, the task remains
`waiting/read_human_control`; its existing deadline is retained. Only this state can
issue manual Viewer tickets for the business session. Refresh restores the same task
without navigating or creating another browser. The initial observation is a snapshot,
not the result of subsequent manual actions.
`POST /api/v1/connections/boss/{id}/read/{task_id}/handback` with empty JSON atomically
fences old input credentials and claims the handback once. It waits for the human
channel to disconnect, then observes the same session without clicking a conversation.
A changed target, login/risk page or missing messages fails verification. Unconfirmed
disconnection retains the lease and an unknown outcome; explicit reconciliation can
release through the guarded lifecycle and closes only on durable release evidence.
Handback never grants messaging permission or reruns a browser action.

The shared execution adapter reserves a fresh browser session only after rechecking the
owned connected resource, current version, active authorization and expiry. It uses the
existing signed `register`/`create`/`revoke`/`release` lifecycle with owner `boss-read`, then
hands page capture to the BOSS adapter as `boss-page-reader`. Capture outcomes close the
attempt as `completed`, `failed`, or `unknown`; an uncertain lifecycle or page result is
never reported as success. This adapter is currently exercised in isolated tests and has
an explicit HTTP prototype consumer. `POST /{id}/read/{task_id}/run` with empty JSON
executes that accepted attempt once within the request; it is not a Temporal worker
and cannot resume after process interruption. `GET /{id}/read` restores the latest owned
task, and `GET /{id}/read/{task_id}/result` restores its bounded structured observation.
No raw HTML or Cookie is persisted in the result. Unusable observations with confirmed
cleanup close as failed; unconfirmed lifecycle outcomes remain unknown.
`POST /{id}/read/{task_id}/reconcile` with empty JSON closes an unknown read as failed
only after matching owned, revoked, lease-free and physically released session evidence.
It revokes the read authorization and never reruns the original attempt.

`POST /api/v1/connections/boss/{id}/login/finish` requires JSON `{version}` and
verifies the active login after stopping the Viewer, saves its encrypted state and
releases the browser before recording `connected`. Unverified state never becomes
connected; an uncertain result requires reading the existing execution.
`DELETE /api/v1/connections/boss/{id}/saved-login` requires the connected resource's
version and confirmed browser release. It removes CareerAct's saved credentials,
then revokes that connection, returning 204. It does not log out the BOSS account
remotely. Old cleanup commands cannot remove a newer login snapshot.

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
