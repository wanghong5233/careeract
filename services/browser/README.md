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
