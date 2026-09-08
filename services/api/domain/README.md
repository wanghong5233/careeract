# Domain

Career profiles, goals, jobs, materials, applications, and communication models live here.

Keep this layer framework-free. Every user-owned aggregate carries its immutable
`user_id`. Repository operations receive the authenticated `ActorContext` and scope
reads and writes by that ID; a caller-supplied resource ID never bypasses the owner
predicate. Cross-user uniqueness uses `(user_id, value)` database constraints rather
than global keys.
