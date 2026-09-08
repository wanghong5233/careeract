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
