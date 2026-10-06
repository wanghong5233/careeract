# CareerAct

CareerAct is a personal career Agent workspace: it helps turn career context,
job goals, and user decisions into reviewable work and durable career records.
It is built as a job-search engineering portfolio project, with the Agent as the
primary product surface rather than a collection of disconnected forms.

## What is implemented

The current baseline includes:

- a Next.js Agent workspace with projects, conversations, archives, side chats,
  branches, message history, and a multi-panel work surface;
- a FastAPI domain backend with Better Auth, PostgreSQL ownership checks, and
  versioned writes;
- an Agno-backed runtime with AG-UI streaming, multi-turn history, selected
  career context, cancellation, failure/unknown states, and run reconciliation;
- a synthetic-materials experiment with versioned drafts, proposals, character-
  level review blocks, partial decisions, and concurrency protection;
- Temporal, browser orchestration, and vendored Agno/browser-use forks prepared
  for later career workflows.

The general Agent workspace is at a handoff baseline. The next business slice is
a synthetic resume targeted-edit flow: Agent request → persisted proposal →
partial user review → refreshed persisted result. Real resumes, uploads, rich
formatting/export, SSE reconnect, cross-process run continuation, and production
deployment remain explicitly out of scope for this baseline.

## Architecture

| Area | Responsibility |
| --- | --- |
| `apps/web` | Next.js Agent shell, Better Auth, same-origin BFF, and workspace UI |
| `services/api/domain` | Framework-independent career objects and rules |
| `services/api/application` | Use cases, transactions, and external capability ports |
| `services/api/infrastructure` | PostgreSQL, Agno, model gateway, auth, and storage adapters |
| `services/api/routes` | REST and AG-UI boundaries |
| `services/worker` | Deterministic Temporal workflows and side-effect activities |
| `services/browser` | Browser sessions, Playwright, browser-use, and site adapters |
| `vendor/` | Project-owned upstream forks imported with `git subtree` |

PostgreSQL is the source of truth for CareerAct domain data. Agent runs, chat
history, Temporal history, and browser pages do not replace domain state.

## Local development

Prerequisites: Windows or Linux, Python 3.11–3.13, Node.js 22, `uv`, npm, and
Docker with Compose. From the repository root:

```powershell
uv sync --frozen --all-packages --group dev
npm --prefix apps/web ci
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path apps/web/.env.local)) { Copy-Item apps/web/.env.example apps/web/.env.local }
```

Fill in the local credentials and provider configuration described in the
[development guide](docs/handbook/DEVELOPMENT.md#配置与启动), then prepare the services:

```powershell
docker compose up -d postgres
uv run --package careeract-api alembic -c services/api/alembic.ini upgrade head
docker compose up -d litellm
uv run --no-sync python scripts/manage_model_key.py provision
npm --prefix apps/web run dev
```

`npm --prefix apps/web run dev` starts Web and API together. It uses the primary
debug pair `43110/43111` and automatically selects the next pair from the fixed
debug pool if either port is occupied. The selected pair is injected into both
services, so authentication and BFF requests cannot drift to different ports.
The launcher reports the selected URL and port conflicts, reuses the existing
instance on repeated starts, and recovers a failed service on its current port
with bounded backoff. Configuration, dependency, and exhausted-port failures
remain visible in `data/dev/careeract.log`. This does not replay Agent requests
or provide persistent Agent Run recovery.

Open the printed Web URL. The API health endpoint is the printed API URL plus
`/health`. Use `npm --prefix apps/web run dev:status` to find the current address
and `npm --prefix apps/web run dev:stop` to stop the instance and its process trees.

The full startup, authentication, migration, model, browser, and troubleshooting
instructions are in [the development guide](docs/handbook/DEVELOPMENT.md#配置与启动).

## Verification

The repository checks are grouped by service:

```powershell
uv run ruff format --check services tests scripts/check_changes.py scripts/check_secrets.py
uv run ruff check services tests scripts/check_changes.py scripts/check_secrets.py
uv run mypy services tests scripts/check_changes.py scripts/check_secrets.py
uv run pytest
Set-Location apps/web
npm run lint
npm run typecheck
npm run test
npm run build
```

See [current status](docs/handbook/STATUS.md) for the latest evidence, known
limits, and the next business increment. The engineering workflow and ownership
boundaries are in [the development handbook](docs/handbook/DEVELOPMENT.md), and
the product requirements and architecture documents are kept private when local
project policy excludes them from a clone.

## Privacy and security boundaries

Secrets, cookies, real resumes, and recruiting screenshots stay outside Git.
External writes require explicit authorization and evidence. The current project
does not claim production DLP, public hosting, real-material processing, or
automatic job application submission.

## License

CareerAct source code is licensed under [Apache License 2.0](LICENSE). Apache-2.0
provides a broad copyright and patent license while requiring preservation of the
license and attribution notices; it does not grant CareerAct trademarks or imply
that private career data may be redistributed. Copyright ownership and third-party
notices are recorded in [NOTICE](NOTICE). Vendored forks and package dependencies
retain their own licenses, including Apache-2.0 and MIT components.
