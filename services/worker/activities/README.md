# Activities

Agent, browser, and external-write activities live here.

Activities are the only Worker layer allowed to perform I/O. Each call propagates the
task, attempt, actor, authorization, and request identifiers and records evidence
before reporting completion.

Read-only and idempotent operations may use bounded retries. Application submission,
message sending, and other external writes with an uncertain result never retry
automatically; they stop for deterministic reconciliation or human review.
