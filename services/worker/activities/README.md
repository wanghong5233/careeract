# Activities

Agent, browser, and external-write activities live here.

Activities are the only Worker layer allowed to perform I/O. Each call propagates the
task, attempt, actor, authorization, and request identifiers and records evidence
before reporting completion.

Recruiting activities send only a durable UUID to the authenticated internal API.
The API derives actor, target, authorization and attempt from owned database records,
then invokes the existing use cases and Browser Service. The Worker has no API imports,
database connection, model credential or Browser signing key. Internal HTTP failures
are sanitized before entering Temporal History; delivery uncertainty never retries a send.

Read-only and idempotent operations may use bounded retries. Application submission,
message sending, and other external writes with an uncertain result never retry
automatically; they stop for deterministic reconciliation or human review.
