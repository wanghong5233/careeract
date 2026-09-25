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

Start with [current status and scope](docs/STATUS.md), then follow the
[local development and validation guide](docs/DEVELOPMENT.md).
The repository currently contains foundations, not a verified job-application product.

Coding agents should read [AGENTS.md](AGENTS.md). Three task-scoped skills and their
sources are described in [Skills guidance](docs/SKILLS.md); no global plugin is required.

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
