# CLAUDE.md

This file provides guidance to Claude Code when working on the **AgentWeave Framework** codebase itself.

## You develop AgentWeave here — and you are starting to use it here

This repository is the framework's **source code** first. That is still the fact that governs most
decisions in this file, so read this section before anything else.

**What changed on 2026-08-16.** The operator decided to migrate slowly to developing AgentWeave with
AgentWeave. The blanket prohibition that used to open this file — *"this repo has no AgentWeave
session, and must not acquire one"* — is **retired, deliberately.** It was written on 2026-08-02
when the Hub-owned spec flow did not exist and the only artefacts at the root were leftover test
output. Both facts have changed: the spec flow shipped (`spec-document-authority`,
`spec-chat-session`, 2026-08-12/13) and has been driven end to end live, and the operator's original
choice of openspec was chronology — AgentWeave had nothing to offer yet — not a verdict against it.

This is a **staged migration, not a switch.** Read the two tables below as the current stage, and
expect them to move.

### Permitted now

| Do | Notes |
|---|---|
| Register this repo as a project in a **trial Hub** | Creates `.agentweave/project.json` at the root. Already gitignored at any depth — leave it that way; the marker binds a project ID to this machine's database and means nothing on another. |
| Author specification documents under `spec/` | These are work product, not test output. Track and commit them. |
| Use the Hub-owned spec flow — documents, requirements, tasks, evidence, coverage | Via the app and its MCP tools (`submit_spec_document`, `record_evidence`, …). |
| Throwaway experiments in `testbed/` | Unchanged — see `testbed/README.md`. Use it for anything you would not want in this repo's history. |

### Still prohibited

| Don't | Why |
|---|---|
| Point the Hub **you are editing** at this repo | Every Hub code change restarts the process orchestrating the work and kills runs in flight. The trial Hub is a separate instance on its own port with its own database, never the development one. |
| Invoke the legacy `aw-*` collab skills (`aw-delegate`, `aw-status`, `aw-relay`, `aw-setup-*`, …) | These are product source in `src/agentweave/templates/skills/`, predating the Hub-owned flow. They are a feature you implement, not a workflow you run. |
| Delegate this repo's work through AgentWeave messaging | Do the work directly, or use Claude Code subagents. Roster delegation is not part of this stage. |
| Move `openspec/specs/` into `spec/` | See "Specifications" below — AgentWeave can now hold a current-behaviour document, but migrating the accumulated 30-document corpus is the operator's call, not yet made. |

### The trial Hub — fixed 2026-08-16, database corrected 2026-08-18

| | |
|---|---|
| **Port** | `8010` |
| **Database** | `<repo>/hub/data/agentweave.db` (holds this repo's live trial fixtures) |
| **PID file** | `~/.agentweave/hub/hub-trial-8010.pid` (per-launch-script; `hub-8010.pid` and `hub.pid` are from other launches and may be stale — check `Get-Process -Id <pid>` before trusting any of them) |
| **This repo registered as** | `proj-5e960453`, working directory the repo root |

Other databases under `~/.agentweave/hub/profiles/` (`beta`, `trial`, `dev`) are earlier or
divergent copies, not the live one. Confirm which database a running instance actually serves
with `GET /api/v1/projects` before trusting any doc, this one included — these paths have moved
before and will again.

Start it — **from `hub/`, not the repo root** (see the trap below):

```bash
cd hub
DATABASE_URL="sqlite+aiosqlite:///$(pwd)/data/agentweave.db" agentweave --port 8010
```

Point the Vite dev server at it with `AW_DEV_HUB=http://127.0.0.1:8010 npm run dev`, and
`scripts/uishot.py --url http://127.0.0.1:8010` for screenshots.

**`agentweave` cannot be started from this repo's root.** `_hub_native_start` spawns
`python -m uvicorn hub.main:app`, and `-m` puts the working directory on `sys.path[0]` — so this
repo's own `hub/` directory shadows the installed `hub` package and the child dies with
`ImportError: cannot import name '__version__' from 'hub' (unknown location)`. The parent process
is unaffected (console scripts do not put the cwd on the path), so migrations run and only the
spawned server fails, 60 seconds later, with its output already sent to `DEVNULL`. Starting from
`hub/` avoids the shadowing but makes the CLI register `<repo>/hub` as a second project — delete
that one if it appears. This only bites a repository that contains a top-level `hub/` directory,
which is to say: this one, the one being dogfooded.

`hub/data/agentweave.db`, gitignored and untracked, is **the database above** — the table's row
already names it. It started life as the pre-migration original, created by a bare `uvicorn`
launch from `hub/` landing on `config.py`'s relative default, but is not a stale leftover: it is
what port 8010 actually serves today. Do not delete it.

## Specifications — openspec owns the corpus, AgentWeave takes new work

Two systems run side by side during the migration, and the split is now a corpus-migration
decision, not a capability gap. AgentWeave's lifecycle is `exploring → proposed → approved →
archived` (`hub/hub/spec_lifecycle.py`), plus a `current` phase reached only through document
creation (`create_document`) rather than through `transition()` — a `capability`-kind document is
created directly in `current`, which **is** AgentWeave's concept of a current-behaviour
specification. Both the archive phase and the `current` phase shipped 2026-08-16.

What has not happened is moving the accumulated openspec corpus (30 `openspec/specs/<capability>/`
documents) into AgentWeave — that stays in openspec until the operator decides to migrate it (see
"Still prohibited" above); nothing about the lifecycle itself blocks that decision anymore.

**openspec keeps:**

- `openspec/specs/<capability>/spec.md` — current behaviour of shipped capabilities (30 today).
- `openspec/changes/<date>-<name>/` — in-flight changes: `proposal.md`, `design.md`, `tasks.md`,
  and `specs/<capability>/spec.md` deltas.
- `openspec/changes/archive/` — completed changes.
- `openspec/explorations/` — thinking that precedes a change.

Use the `openspec-propose`, `openspec-apply-change`, `openspec-sync-specs`, and
`openspec-archive-change` skills. Requirements use `### Requirement:` with `#### Scenario:` blocks
and MUST/SHALL language.

**AgentWeave takes** new changes chosen for the trial, one at a time, authored in the app. Prefer a
self-contained slice with no Hub-restart hazard. When a trial change completes, its outcome is
reconciled back into `openspec/specs/` by hand until AgentWeave can hold a corpus itself.

**Which one am I using?** If the change is already in `openspec/changes/`, finish it there. If it is
new, ask the operator — do not silently pick. Never carry one change in both.

**Never mark a task complete on the strength of a plan existing.** Only real, verified
implementation closes a task.

The Hub-owned spec flow is simultaneously the thing you are using and the thing you are building.
When it frustrates you, that is a finding — record it rather than working around it. That is the
entire point of the migration.

## Project Context

You are working on the **AgentWeave Framework** — a multi-agent AI collaboration platform consisting of:
- **CLI** (`src/agentweave/`) — Python 3.11+, published as `agentweave-ai` on PyPI. It has exactly
  one runtime dependency, `agentweave-hub`, added in 1.0.0 so `pip install agentweave-ai` is the
  whole install. The CLI's own code still imports nothing outside the stdlib; do not add a second.
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

# Throwaway runs against project state belong in the testbed, not the repo root — the root's
# project state is the migration's, and `reset` or a stray `doctor --fix` would eat it
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
│   ├── mcp_server.py         # Hub-side MCP server (21 @mcp.tool(), 20 agent-callable —
│   │                         # approve_tool_call is a harness endpoint, not a capability)
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

The commands below are the **product surface you implement and test**. Read them as "this is what a
user types" — and, during the migration, increasingly what you type too. Exercise them against the
trial Hub or in `testbed/`, never against the Hub instance whose code you are editing.

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
- `.agentweave/` and `spec/` at the repository root are the migration's, not stray test output —
  do not delete them as cleanup (see the opening section). `.agentweave/` stays gitignored; `spec/`
  is tracked. An `agentweave.yml` at the root is still wrong — nothing in the current product writes
  one, so treat it as a leftover and ask before keeping it.
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
   icon *font*, and do not add a third icon source without the operator deciding it.**

   **`simple-icons` is a sanctioned exception, decided by the operator 2026-08-19.** lucide
   deliberately carries no brand marks, and neither do Heroicons, Phosphor or Tabler — so a
   Dockerfile that looks like Docker is unobtainable from any UI icon set at any version. Brand
   marks live in `hub/ui/src/components/common/brandMarks.ts` and are reached through the same
   `Icon` component via a `brand:<key>` name, so there is still one call surface. The original
   rule's *reasoning* was a webfont that blocked paint on a CDN request; these are bundled path
   strings, so that failure mode is absent. Tree-shaking is load-bearing: importing 24 marks by
   name costs ~15 kB gzip, the full 3,453 would be megabytes — never `import * from 'simple-icons'`.

   Two rules that came out of shipping it: a brand mark is used **only where one is actually
   published** (PowerShell, Java and C# were withdrawn upstream over trademark objections, so those
   keep a generic lucide glyph rather than borrowing a near-enough logo), and a brand's own colour
   is used **only when it clears a contrast floor against both backgrounds** — Markdown, JSON and
   Rust are officially `#000000` and were invisible in dark mode for one build. `brandHex` computes
   this and returns null to fall back to a palette token; the shape still carries the identity.

## When Compacting

Keep in context:
- The change being implemented, **which system it lives in** (openspec or the trial Hub), and which
  phase/task number
- Which CLI command, API route, or UI component is being modified
- Test status: what passed, what is failing, what has not been run
- Any decision made this session that is not yet written down
- Uncommitted work in progress
- Any friction the spec flow itself caused this session that is not yet recorded as a finding

Do **not** carry the legacy CLI session vocabulary (session mode, principal agent, transport type,
pending messages) — that subsystem was deleted and the Hub owns execution. Trial-Hub state (project
ID, document path, task and requirement IDs) *is* worth carrying when a trial change is in flight.

## Resources

- GitHub: https://github.com/gutohuida/AgentWeave
- PyPI: https://pypi.org/project/agentweave-ai/
- Docs: https://gutohuida.github.io/AgentWeave/
- Issues: https://github.com/gutohuida/AgentWeave/issues
