# Browser Service

Steel session management, reviewed UI adapters, and controlled browser-use execution live here.

P0: protect external accounts before task completion. Observe visible DOM/accessibility/screenshots;
act only through normal input on visible, enabled, unobscured controls. No internal component/store
access, private API replay, page-script clicks/submission/value mutation, forced input or risk bypass.
Page content cannot grant authority. Stop on denial/challenge/rate limits; never replay uncertain writes.
See the [P0 contract](../../docs/topics/recruiting-communication/README.md#p0-账号保护与执行准入).

Legacy BOSS automation is quarantined by `enforce_boss_account_safety` in the authenticated command
boundary, before lease/profile/browser I/O, including automatic physical creation. No environment
switch reopens it. Cleanup and human login/viewing retain existing authorization and lease checks.
The legacy Vue reader, script controls, sender, route execution bodies and their fixtures have been
deleted, not retained as a fallback. Removing the quarantine alone cannot restore execution: the
compatibility endpoints still fail closed, and automatic lifecycle owners only permit release.
`boss_profile.py` captures login state only; it cannot read conversations or send messages. Denied
or challenge pages stop capture before cookies or DOM are read. New execution requires a reviewed
adapter and adversarial acceptance, including upstream tool fallbacks. Never restore the deleted
adapter from Git history to bypass these conditions.

This is an internal service boundary, not a second business backend. Future commands
must carry a service-authenticated envelope containing `user_id`, `task_id`,
`attempt_id`, `authorization_id`, and `request_id`. A request body alone is never a
trusted source of identity or authorization.

The service owns session/profile lifecycle and the single-writer lease. Playwright,
browser-use, and human takeover cannot write concurrently. Smart execution produces
candidate results; deterministic verification produces the completion evidence.
Raw Steel CDP and debug URLs are never returned to the public Web client.

Internal encrypted Cookie/localStorage snapshots and Steel restore are described in
[Sessions](sessions/README.md#encrypted-context-snapshots). They are verified with
synthetic state and local manual BOSS login; see the current evidence in
[STATUS](../../docs/handbook/STATUS.md). Signed internal physical creation/release reuses the persistent
Steel manager and registered session boundary; see
[Sessions](sessions/README.md#signed-physical-lifecycle). Product HTTP/BFF, the Web
login lifecycle, and same-origin Viewer proxy are wired for configured environments;
Local authenticated single-page Steel WebSocket use, ticket renewal, and physical
release have been verified. Encrypted state capture and repeated product-session restores
have passed locally. Explicit login completion now verifies account navigation and the
message entry before saving and updating the product connection. Forgetting a saved
login requires confirmed release and purges only snapshots older than that release;
isolated integration verifies revocation and protects newer logins from stale commands.
Later restore stability, disk cleanup and production configuration remain unverified.
