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

## Local development

```powershell
Copy-Item .env.example .env
docker compose up -d
uv sync --frozen --all-packages
uv run --package careeract-api alembic -c services/api/alembic.ini upgrade head
uv run --package careeract-api uvicorn services.api.app.main:app --reload
```

Run the web workspace in another terminal:

```powershell
Set-Location apps/web
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Run the internal services when working on durable or browser tasks:

```powershell
uv run --package careeract-worker python -m services.worker.app.main
uv run --package careeract-browser uvicorn services.browser.app.main:app --port 8001 --reload
```

Local endpoints:

- Workspace: `http://localhost:3000`
- AgentOS / AG-UI: `http://localhost:8000`
- LiteLLM: `http://localhost:4000`
- Temporal UI: `http://localhost:8233`
- Steel: `http://localhost:3001`

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
