# Workflows

Durable career and job-search workflows live here.

Workflows contain deterministic orchestration only. They may schedule Activities,
timers, signals, updates, and child workflows, but never perform network, database,
filesystem, model, or browser I/O.

Long-running product tasks distinguish `accepted`, `running`, `waiting`, `failed`,
`timed_out`, `cancelled`, and `completed`. Cancellation and user input arrive through
Workflow messages. Checkpoints describe confirmed business progress, not ephemeral
browser DOM state.
