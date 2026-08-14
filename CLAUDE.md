# CLAUDE.md

This file provides guidance to Claude Code when working on the **AgentWeave Framework** codebase itself.

## You develop AgentWeave here — you do not use it here

This repository is the framework's **source code**, not a project that runs the framework. The
distinction governs almost every decision in this file, so read it before anything else.

**This repo has no AgentWeave session, and must not acquire one.** There is no `agentweave.yml`, no
`.agentweave/`, no `spec/`, and no generated `.claude/skills/aw-*`. They were removed on 2026-08-02
because they were test output that read as project state. Do not recreate them at the repository
root.

| Don't | Do |
|---|---|
| Launch the app or point a Hub at the repo root | Do it inside `testbed/` (see `testbed/README.md`) |
| Invoke `aw-*` skills (`aw-spec-propose`, `aw-status`, `aw-delegate`, …) | Use the `openspec-*` skills — see "Specifications" below |
| Delegate to agents via AgentWeave messaging | Do the work directly, or use Claude Code subagents |
| Write to `spec/` | Write to `openspec/changes/<date>-<name>/` |
| Treat `agentweave.yml` / `.agentweave/` as configuration to read | Treat them as *product surfaces you implement* |

The `aw-*` skills and the aw-spec workflow are **features AgentWeave ships to its users**
(`openspec/specs/aw-spec-workflow/spec.md`, `src/agentweave/spec_manifest.py`,
`hub/hub/api/v1/spec.py`, `hub/ui/src/components/spec/`, `src/agentweave/templates/skills/`). Change
that code when the feature needs changing; never run it against this repo.

## Specifications — this repo uses openspec

All planned work lives in `openspec/`:

- `openspec/specs/<capability>/spec.md` — current behaviour of shipped capabilities.
- `openspec/changes/<date>-<name>/` — one in-flight change: `proposal.md`, `design.md`,
  `tasks.md`, and `specs/<capability>/spec.md` deltas.
- `openspec/changes/archive/` — completed changes.

Use the `openspec-propose`, `openspec-apply-change`, `openspec-sync-specs`, and
`openspec-archive-change` skills. Requirements use `### Requirement:` with `#### Scenario:` blocks
and MUST/SHALL language.

**Never mark a task complete on the strength of a plan existing.** Only real, verified
implementation closes a task.

## Project Context

You are working on the **AgentWeave Framework** — a multi-agent AI collaboration platform consisting of:
- **CLI** (`src/agentweave/`) — Python 3.8+, zero runtime dependencies, published as `agentweave-ai` on PyPI
- **Hub** (`hub/`) — FastAPI backend + React/Vite dashboard, self-hosted via Docker
- **Documentation** (`docs/`) — MkDocs with Material theme, deployed to GitHub Pages

Current version: see `pyproject.toml` (CLI) and `hub/pyproject.toml` (Hub) — those are the
single source of truth; version numbers repeated in prose go stale.

## Quick Commands

### Development Setup

```bash
# CLI (editable install)
pip install -e ".[dev,mcp]"

# Verify the editable install resolves (safe at the repo root — reads no project state)
agentweave --help
aw --help

# Anything that touches project state belongs in the testbed, never the repo root
cd testbed/scratch && agentweave doctor

# Hub (Docker)
cd hub && docker compose up -d

# Hub UI (hot-reload)
cd hub/ui && npm install && npm run dev  # http://localhost:5173

# Documentation
mkdocs serve  # http://localhost:8000
```

### Code Quality

```bash
# Python (CLI)
ruff check src/
black src/
mypy src/

# TypeScript (Hub UI)
cd hub/ui && npm run lint
```

### Testing

```bash
# CLI tests
pytest tests/ -v

# Hub tests
pytest hub/tests/ -v

# All tests
make test-all
```

## Architecture Overview

### Local multi-project boundary

One local Hub instance owns a collection of projects. A project's database ID is durable and its
canonical working directory is a unique binding recorded by a non-secret
`.agentweave/project.json` marker. Operator APIs include explicit project IDs in their routes,
frontend server-state keys are project-prefixed, and the instance operator SSE stream stamps each
event with its trusted project ID.

Resolve every project filesystem path through `ProjectWorkspace`; never use the Hub process's
`Path.cwd()` as project identity. Native mode can open valid local directories. Docker mode accepts
only container-visible paths beneath `AW_WORKSPACE_ROOT`, mounted from
`AW_WORKSPACE_HOST_ROOT`, without Docker-socket access or host-path guessing.

### CLI (`src/agentweave/`)

The CLI is **not** a collaboration surface. It does only what cannot be done from inside the app:
start it, diagnose why it will not start, stop it, reset it. Five `cmd_*` functions survive, down
from 56 — see `openspec/explorations/2026-08-02-product-direction.md` for why, before adding a
sixth.

```
src/agentweave/
├── cli.py              # The 5 surviving commands: status, doctor, stop, hub_start, reset.
│                       # To add: cmd_* function, subparser in create_parser(), routing in main()
├── diagnostics.py      # What `doctor` reports on: runtimes, ports, database, permissions
├── config.py           # agentweave.yml parsing and generation
├── session.py          # Session lifecycle, JSON persistence
├── task.py             # Task CRUD, file-based storage with locking
├── jobs.py             # Scheduled-job records
├── locking.py          # File-based mutex (use: `with lock("name"):`)
├── validator.py        # validate_task/message/session + sanitize functions
├── eventlog.py         # Read-path utilities for events.jsonl
├── stream_events.py    # Canonical run-event kinds shared with the Hub's parsers
├── tool_surface.py     # The agent capability surface description
├── spec_manifest.py    # Spec manifest read/write
├── logging_handlers.py # JSONRotatingFileHandler + HubHandler
├── constants.py        # All valid values, regex patterns, directory paths
├── utils.py            # load_json, save_json, generate_id, now_iso, print_* helpers
├── templates/          # Markdown templates loaded via get_template("name")
│   └── skills/         # Packaged skill templates (handoff, resume, generated aw-*)
├── transport/          # HTTP only — the Hub is the single runtime
│   ├── base.py         # BaseTransport ABC
│   ├── http.py         # HTTP transport for the Hub
│   └── config.py       # get_transport() factory
└── mcp/
    └── server.py       # Compatibility re-export of the Hub's tool surface — no tools of its own
```

**Deleted, and not to be recreated:** `watchdog.py`, `messaging.py`, `runner.py`,
`transport/local.py`, `transport/git.py`, and the role subsystem. The Hub owns execution; there is
no second runtime and no filesystem or git collaboration substrate.

### Hub (`hub/`)

```
hub/
├── hub/                      # Python package
│   ├── main.py               # FastAPI app factory + lifespan
│   ├── mcp_server.py         # Hub-side MCP server (11 tools)
│   ├── data/charters/        # Starter charter seed documents + manifest
│   ├── db/                   # SQLAlchemy async models and migrations
│   │   ├── models.py
│   │   └── engine.py
│   ├── api/v1/               # REST endpoints
│   │   ├── agents.py         # Agent roster, bindings, and canonical context
│   │   ├── runners.py        # Runner registry CRUD
│   │   ├── charters.py       # Charter CRUD
│   │   ├── messages.py       # Messages CRUD
│   │   ├── tasks.py          # Tasks CRUD
│   │   ├── questions.py      # Human Q&A
│   │   ├── events.py         # SSE endpoint for real-time updates
│   │   ├── logs.py           # Agent output logs
│   │   ├── agent_chat.py     # Per-agent chat history
│   │   ├── agent_trigger.py  # POST /api/v1/agent/trigger
│   │   └── session_sync.py   # Session sync endpoint
│   └── schemas/              # Pydantic schemas
├── ui/                       # React dashboard
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api/              # React Query hooks
│   │   │   ├── agents.ts     # useAgents, useAgentOutput, useAgentSessions
│   │   │   ├── messages.ts   # useMessages, useMessageHistory
│   │   │   ├── tasks.ts
│   │   │   ├── agentChat.ts  # useAgentChatHistory
│   │   │   └── ...
│   │   ├── components/
│   │   │   ├── agents/       # Agent UI
│   │   │   │   ├── AgentsPage.tsx
│   │   │   │   ├── AgentCard.tsx          # Runner/model and status summary
│   │   │   │   ├── AgentOutputPanel.tsx   # Live output logs
│   │   │   │   ├── AgentActivityTab.tsx   # Output + timeline events
│   │   │   │   └── AgentInfoTab.tsx
│   │   │   ├── tasks/        # TaskBoard, TaskCard
│   │   │   ├── messages/     # MessagesFeed, MessageCard, ConversationGroup
│   │   │   ├── questions/    # QuestionsPanel, AnswerForm
│   │   │   ├── logs/         # LogsView, LogLine
│   │   │   ├── activity/     # ActivityLog, EventRow
│   │   │   ├── layout/       # Sidebar, StatusBar, SetupModal
│   │   │   └── common/       # Badge, Icon, EmptyState
│   │   ├── store/            # Zustand stores (configStore)
│   │   └── hooks/            # useSSE, useCopy
│   └── package.json
├── docker-compose.yml
└── Dockerfile
```

## Shipped features and their user-facing commands

The commands below are the **product surface you implement and test**, not a workflow to run in this
repo. When you need to exercise one, do it in `testbed/`. Read them as "this is what a user types."

### Runner, Agent, and Charter Separation

The Hub owns three independent project-scoped concepts:

- runners describe reusable execution capability (`claude`/`codex`, model, and flags);
- agents are addressable roster identities bound to at most one runner and one charter;
- charters are editable markdown behavior contracts injected into canonical turn context.

Fresh projects seed default runners and the starter charters declared in
`hub/hub/data/charters/charters.json` (9 today). Operators manage and bind them through
the Hub UI. The former CLI multi-role subsystem, fixed enum, role files, and role-derived API/UI
fields no longer exist and must not be recreated.

### Runners

A runner is a Runner record in the Hub — a CLI (`claude`, `codex`, …), a model, and flags. Operators
create and bind them in the Hub UI; `hub/hub/runner_commands.py` turns one into a spawn. Claude and
Codex are the two wired to a real spawn path today; the rest are refused with a stated 501 rather
than silently mishandled.

### Operator-in-the-loop

An agent can stop and involve the operator rather than guess:

- **Permissions** — the composer's Permissions pill sets the run's posture. `manual` ("Ask me")
  routes Claude through `--permission-prompt-tool` and Codex through
  `codex_appserver.decide_approval`, producing a card the operator answers.
- **Questions** — `ask_user` takes 1–4 structured questions, blocks, and returns the answers. The
  operator steps through them above the composer.
- **The backstop** — a completed run whose final text ends in a question, having opened no question
  row, is flagged so a question the agent forgot to route still reaches the operator.

How long a run waits is per-agent (`Agent.permission_timeout_seconds`,
`Agent.question_timeout_seconds`), carried to the spawned tool process as `AW_DECISION_TIMEOUT` and
`AW_QUESTION_TIMEOUT`.

### Logging

Python `logging` stdlib, set up in `logging_handlers.py`:
- `JSONRotatingFileHandler`: 10MB rotation, 5 backups → `.agentweave/logs/events.jsonl`
  *(inside a project, never at this repo's root)*
- `HubHandler`: forwards to the Hub

Env vars: `AW_LOG_LEVEL` (default WARNING), `AW_LOG_FILE`

## Hub UI Patterns

### Adding a Component

1. Create component in `hub/ui/src/components/{category}/ComponentName.tsx`
2. Use existing components (Badge, Icon, EmptyState) for consistency
3. Add to barrel export if applicable
4. Use React Query for data fetching (see `hub/ui/src/api/`)

### Adding an API Hook

```typescript
// hub/ui/src/api/feature.ts
import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

export function useFeature() {
  const { isConfigured } = useConfigStore()
  return useQuery({
    queryKey: ['feature'],
    queryFn: () => getJson('/api/v1/feature'),
    enabled: isConfigured,
  })
}
```

### Real-time Updates

Hub uses SSE (Server-Sent Events) for live updates:
- `useSSE` hook in `hub/ui/src/hooks/useSSE.ts`
- Events: `agent_output`, `session_synced`, `task_updated`, etc.
- Frontend invalidates React Query cache on events

## Task Status Lifecycle

```
pending → assigned → in_progress → completed → under_review → approved
                                             ↘ revision_needed
                                             ↘ rejected
```

## Critical Rules

- Agent names validated by `AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")` — any match accepted
- `VALID_MODES = ["hierarchical", "peer", "review"]`
- ALL saves pass through `validator.py` sanitize functions
- ALL task modifications use `with lock("name"):`
- Templates via `get_template("name")` — never hardcode in `cli.py`
- `is_locked()` is read-only — never delete files
- NEVER create `.agentweave/`, `agentweave.yml`, or `spec/` at the repository root — use `testbed/`
- NEVER commit `kimichanges.md`, `kimiwork.md`
- Hub API key format: `aw_live_{random32}`; run credentials are minted per run (`agent_auth.py`) and
  identity is never accepted from a request body or header
- HttpTransport uses stdlib `urllib.request` only
- `hub/hub/mcp_server.py` is spawned standalone and may import **only** stdlib + fastmcp — anything
  it needs from the Hub is restated there, with a test asserting the two agree
- `approve_tool_call` has **no return annotation**. FastMCP would derive `structuredContent` from
  one, which silently defeats an `allow`. Do not add one.
- `hub/hub/static/ui` is a committed build artefact. After `cd hub/ui && npm run build`, run
  `make ui` (or `python scripts/refresh_ui_bundle.py` directly — `make` is not on PATH in Git Bash
  on this machine) — it copies `dist/` over it, confirms the copy, and records
  `hub/hub/static/ui/ui-build-stamp.json`, the fingerprint of the source it was built from. Commit
  `hub/ui/src` and `hub/hub/static/ui` together; the stamp is what gives a byte-identical rebuild
  something to commit, so `/health` can stop reporting `ui_stale`. Only the script writes the
  stamp. `test_ui_staleness.py` still does **not** check this repo's copy;
  `test_ui_build_stamp.py` checks the stamp parses, and gates the stricter
  bundle-matches-source assertion behind `AW_CHECK_UI_BUNDLE=1`.
- Stage paths explicitly; `git add -A` sweeps in scratch

## Common Tasks

### Adding a CLI Command

1. Add `cmd_<name>()` function in `cli.py`
2. Add subparser in `create_parser()`
3. Add routing branch in `main()`
4. Add tests in `tests/test_cli.py`

### Adding a database column

1. Add the field in `hub/hub/db/models.py`
2. New migration in `hub/hub/migrations/versions/` — guard for a missing table, as `0033`/`0034` do,
   because upgrades starting from an early revision reach it with only that revision's tables
3. Bump the head assertions in `hub/tests/test_migrations.py` **and**
   `hub/tests/test_project_persistence.py`
4. Expose it on the relevant Pydantic schema if the UI needs it

### Adding an MCP Tool

1. Add `@mcp.tool()` decorated function in `hub/hub/mcp_server.py`
2. Import and use existing core modules
3. Follow existing error handling patterns

### Adding a UI Component

1. Create in `hub/ui/src/components/{category}/`
2. Use TypeScript + functional components
3. Use Tailwind CSS + CSS variables for theming
4. Use React Query for data, Zustand for global state
5. Use the `Icon` component — it wraps `lucide-react` SVGs. The Material Symbols webfont was
   removed (it loaded `display=block` from a CDN and held every icon invisible until the request
   completed). The `name` API was kept so call sites did not change. **Do not reintroduce a second
   icon system.**

## When Compacting

Keep in context:
- The openspec change being implemented, and which phase/task number
- Which CLI command, API route, or UI component is being modified
- Test status: what passed, what is failing, what has not been run
- Any decision made this session that is not yet written into `openspec/`
- Uncommitted work in progress

Do **not** carry AgentWeave session state (task IDs, session mode, principal agent, transport type,
pending messages). This repo has no session — if that seems relevant, something was run at the repo
root that should have run in `testbed/`.

## Resources

- GitHub: https://github.com/gutohuida/AgentWeave
- PyPI: https://pypi.org/project/agentweave-ai/
- Docs: https://gutohuida.github.io/AgentWeave/
- Issues: https://github.com/gutohuida/AgentWeave/issues
