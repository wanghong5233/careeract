# Browser Service

Steel session management, Playwright adapters, and controlled browser-use execution live here.

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
have passed locally. Later restore stability, durable connection-state updates,
joint browser/profile revocation and production configuration remain unverified.
