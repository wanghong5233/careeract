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
- `docs`: product and architecture decisions

See [PRD](docs/PRD.md) and [Architecture](docs/ARCHITECTURE.md).

## Local development

```powershell
Copy-Item .env.example .env
docker compose up -d
uv sync
uv run uvicorn services.api.app.main:app --reload
```

Run the web workspace in another terminal:

```powershell
Set-Location apps/web
Copy-Item .env.example .env.local
npm install
npm run dev
```

Local endpoints:

- Workspace: `http://localhost:3000`
- AgentOS / AG-UI: `http://localhost:8000`
- LiteLLM: `http://localhost:4000`
- Temporal UI: `http://localhost:8233`
- Steel: `http://localhost:3001`

The code in `vendor/` is imported from the project-owned GitHub forks with
`git subtree`. It remains editable in this repository while retaining an
explicit upstream history.
