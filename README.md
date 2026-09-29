# CareerAct

Your personal career agent.

CareerAct is a web-first agent workspace for career planning, job applications,
recruiting communication, interview preparation, and long-term career records.

## Repository

- `apps/web`: Next.js Agent Workspace
- `services/api`: FastAPI domain backend and Agno AgentOS host
- `services/worker`: Temporal workflows and activities
- `services/browser`: Steel, Playwright, and browser-use orchestration
- `vendor/agno`: editable Agno fork
- `vendor/browser-use`: editable browser-use fork

## Development

Core product and architecture documents stay at the top of `docs/` when available
locally. Contributor guides and current status live in `docs/engineering/`;
active implementation plans live in `docs/engineering/plans/`. Directory and
maintenance rules are defined in [AGENTS.md](AGENTS.md#documentation).

Start with [current status and scope](docs/engineering/STATUS.md), then follow the
[local development and validation guide](docs/engineering/DEVELOPMENT.md).
The repository currently contains foundations, not a verified job-application product.
The first working business slice is a manually confirmed career profile with persistent
storage, ownership checks and stale-write protection; the Agent does not yet read it.

Coding agents should read [AGENTS.md](AGENTS.md). Three task-scoped skills and their
sources are described in [Skills guidance](docs/engineering/SKILLS.md); no global plugin is required.

`compose.yaml` contains local infrastructure. The complete domestic
self-hosting topology is defined in `deploy/compose.yaml`; it keeps PostgreSQL,
Temporal, LiteLLM, Steel, API, Worker, Browser Service and their internal ports
off the public network and exposes only Caddy.

The code in `vendor/` is imported from the project-owned GitHub forks with
`git subtree`. It remains editable in this repository while retaining an
explicit upstream history. See `vendor/README.md` for synchronization commands.

## License

CareerAct is licensed under Apache-2.0. Vendored and package dependencies retain
their own copyright and license terms.
