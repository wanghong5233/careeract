# CareerAct

**Your personal career Agent.**

English | [简体中文](README.zh-CN.md)

**Plan your career. Put the next step into action.**

CareerAct is an open-source, agent-native product designed to manage job search
and career development as ongoing projects. It brings career goals, experience,
opportunities, applications, and preparation into one continuous relationship
with a personal Agent.

You set the direction, share feedback, and make the decisions. The Agent connects
the relevant context, organizes the work, creates materials, and carries out
tasks within your authorization. The product spans the career journey—from a
first job search to a career transition and growth after joining a team.

## Why CareerAct

Career work is fragmented. Goals live in notes, experience in resume files,
applications in spreadsheets, and recruiter conversations on separate platforms.
An AI assistant may help with one document, but you still have to explain your
background again, coordinate the next steps, and recover the history when you
return.

CareerAct's central idea is to **treat each career stage as a project, with an
Agent responsible for moving the work forward**. A role connects to the reasons
for pursuing it, the materials submitted, recruiter conversations, and interview
preparation. New experience and decisions become context for the next project.

## What makes it agent-native

- **Goals organize the work.** A graduate job search, a career transition, or a
  skill-development plan has its own goals, constraints, tasks, and milestones.
  A shared career profile connects these projects over time.
- **The Agent leads the work.** Natural-language delegation is the starting
  point. The Agent selects context, drafts outcomes, and coordinates actions;
  documents, comparisons, and browser views support the task at hand.
- **Collaboration happens on the outcome.** Review a material's changes, inspect
  its sources, give feedback, and continue refining the same versioned artifact.
  Confirmed experience stays separate from the way it is presented.
- **Execution has a defined scope.** An action is tied to a role, a material
  version, and an authorization. Its result must be checked against the external
  source. You retain control of factual confirmation, external commitments, and
  career decisions.
- **Progress becomes reusable context.** Application records, interview feedback,
  project evidence, and experience after joining a team contribute to future
  preparation and decisions.

## Career work, connected

The product design brings six areas together:

| Area | Purpose |
| --- | --- |
| Career planning and projects | Turn a stage goal into priorities, tasks, milestones, preparation, and review |
| Career profile and evidence | Maintain experience, skills, achievements, constraints, and the evidence behind them |
| Opportunity discovery and assessment | Find roles from company recruiting sources and platforms; assess fit, eligibility, deadlines, and application constraints |
| Materials and applications | Prepare role-specific materials, retain submitted versions, and coordinate form filling, submission, and follow-up |
| Recruiting communication and preparation | Connect recruiter conversations, company research, interview questions, practice, and offer comparisons to the relevant role |
| Ongoing delegation | Define bounded responsibilities for monitoring opportunities, handling messages, and organizing notifications, with pause and revocation controls |

Official company recruiting sources provide firsthand role information and
application entry points. Platforms such as BOSS Zhipin and Liepin complement
them with opportunities and recruiter communication.

### From a goal to a career record

A request such as “Help me pursue AI engineering roles that fit my background”
connects the whole process:

1. Establish the project's direction, constraints, and relevant experience.
2. Find opportunities and explain the evidence for pursuing or skipping a role.
3. Prepare materials for review and retain the version used for each application.
4. Carry out authorized communication and application steps, then verify results.
5. Organize follow-up and interview preparation around the actual role and submitted materials.
6. Record feedback and decisions, and use them to refine the next step.

The same project structure supports learning plans, portfolio work, and career
transitions. Experience accumulated after a job search remains part of the
person's career history.

## Architecture

The architecture separates career records, Agent reasoning, and task execution.
PostgreSQL holds the business state; Agent runs, conversation history, and browser
sessions reference those records.

| Layer | Architecture |
| --- | --- |
| Agent interaction | Next.js, React, assistant-ui, AG-UI, and shadcn/ui |
| Identity and domain services | Better Auth, a same-origin BFF, and FastAPI |
| Agent runtime and models | Agno AgentOS and LiteLLM |
| Career records | PostgreSQL and versioned domain objects |
| Durable task orchestration | Temporal workflows and activities |
| Browser execution | Steel sessions, Playwright site adapters, and browser-use for changing or unfamiliar pages |

CareerAct owns the career semantics, authorization policies, and result
verification. Established open-source components supply the underlying runtime
and infrastructure. Project-owned Agno and browser-use forks are pinned in
`vendor/` through `git subtree`.

## Local setup

Prerequisites: Windows or Linux, Python 3.11–3.13, Node.js 22, `uv`, npm, and
Docker with Compose. From the repository root:

```powershell
uv sync --frozen --all-packages --group dev
npm --prefix apps/web ci
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path apps/web/.env.local)) { Copy-Item apps/web/.env.example apps/web/.env.local }
```

Configure database, authentication, and model credentials using the
[development guide](docs/handbook/DEVELOPMENT.md#配置与启动), then start PostgreSQL:

```powershell
docker compose up -d postgres
```

Once PostgreSQL is healthy:

```powershell
uv run --package careeract-api alembic -c services/api/alembic.ini upgrade head
docker compose up -d litellm
```

Once LiteLLM is ready:

```powershell
uv run --no-sync python scripts/manage_model_key.py provision
npm --prefix apps/web run dev
```

Open the URL printed by the launcher. See the
[development guide](docs/handbook/DEVELOPMENT.md) for service configuration,
verification, and troubleshooting, and [contributor instructions](AGENTS.md) for
engineering conventions.

## License

CareerAct source code is licensed under [Apache License 2.0](LICENSE).
Attribution and third-party notices are recorded in [NOTICE](NOTICE).
Vendored projects and dependencies retain their own licenses.
