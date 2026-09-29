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

Before exposing execution, replace process-local state with durable coordination
and enforce ownership at the connection/execution boundary. Checking a lease and
then separately sending CDP commands is not atomic. Restarting this prototype loses
state and must never authorize reuse of a surviving Steel session.

Integration sequence and acceptance gates: [browser safety plan](../../../docs/BROWSER_SAFETY_PLAN.md).
