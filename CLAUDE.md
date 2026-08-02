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
| Run `agentweave init`, `switch`, `watch`, `roles`, or start a Hub at the repo root | Run them inside `testbed/` (see `testbed/README.md`) |
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

### CLI (`src/agentweave/`)

```
src/agentweave/
├── cli.py              # All CLI commands. To add: cmd_* function, subparser in create_parser(),
│                       # routing branch in main()
├── session.py          # Session lifecycle, JSON persistence
├── task.py             # Task CRUD, file-based storage with locking
├── messaging.py        # MessageBus — routes through transport layer
├── locking.py          # File-based mutex (use: `with lock("name"):`)
├── validator.py        # validate_task/message/session + sanitize functions
├── watchdog.py         # Polls for new messages/tasks, auto-pings agents
├── eventlog.py         # Read-path utilities for events.jsonl
├── logging_config.py   # Python logging stdlib setup (JSONRotatingFileHandler, HubHandler)
├── runner.py           # Agent runner helpers (claude_proxy support, env var resolution)
├── roles.py            # Multi-role agent management (v0.15.0)
├── constants.py        # All valid values, regex patterns, directory paths
├── utils.py            # load_json, save_json, generate_id, now_iso, print_* helpers
├── templates/          # Markdown templates loaded via get_template("name")
│   ├── roles/          # Role-specific behavioral guides
│   └── ...
├── transport/          # Pluggable transport layer
│   ├── base.py         # BaseTransport ABC (6 abstract methods)
│   ├── local.py        # Local filesystem transport
│   ├── git.py          # Git orphan branch transport (plumbing only)
│   ├── http.py         # HTTP transport for Hub
│   └── config.py       # get_transport() factory
└── mcp/
    └── server.py       # FastMCP server (stdio transport)
```

### Hub (`hub/`)

```
hub/
├── hub/                      # Python package
│   ├── main.py               # FastAPI app factory + lifespan
│   ├── mcp_server.py         # Hub-side MCP server (11 tools)
│   ├── db/                   # SQLAlchemy async models (5 tables)
│   │   ├── models.py
│   │   └── engine.py
│   ├── api/v1/               # REST endpoints
│   │   ├── agents.py         # GET /api/v1/agents (+ roles, sessions, runner)
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
│   │   │   │   ├── AgentCard.tsx          # Role badges, runner badge
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

> **Planned removal:** the multi-role system (`agentweave roles`, `roles.py`, `roles.json`,
> `VALID_ROLE_IDS`, and the 21 guides under `templates/roles/`) is slated for replacement by
> runner/agent/charter separation. See the slice table in
> `openspec/changes/2026-08-02-agent-conversation-workspace/design.md`. Don't build new work on
> roles without checking that first.

### Multi-Role Agent System

Agents can have multiple roles assigned:

```bash
# CLI commands
agentweave roles list
agentweave roles add <agent> <role>
agentweave roles set <agent> <role1,role2,...>
agentweave roles available
```

Role guides auto-copied to `.agentweave/roles/{role}.md`.

### Claude-Proxy Agents

Run Minimax, GLM through Claude Code CLI:

```bash
# Configure
agentweave agent configure minimax --runner claude_proxy

# Built-in providers: minimax, glm

# Run
agentweave run --agent minimax "task"
# or
eval $(agentweave switch minimax)
```

### OpenCode Agents

Run OpenCode (terminal-based AI coding agent) with local Ollama or cloud models:

```bash
# Configure in agentweave.yml
#   opencode-dev:
#     runner: opencode
#     model: ollama/qwen2.5-coder:7b

# MCP setup writes opencode.json automatically
agentweave mcp-setup

# Launch
agentweave switch opencode-dev
```

OpenCode uses stable session IDs (`agentweave-{agent}`) and file-based MCP registration via `opencode.json`.

### Transport Layer

```
No transport.json  → LocalTransport (default)
type: "git"        → GitTransport (cross-machine)
type: "http"       → HttpTransport (Hub)
```

**GitTransport principles:**
- Uses git plumbing only (`hash-object`, `mktree`, `commit-tree`, `push`)
- Never touches working tree or HEAD
- Append-only with UUID-suffixed filenames

**HttpTransport:**
- Uses stdlib `urllib.request` only
- No new CLI dependencies

### Logging (v0.11.0+)

Python `logging` stdlib with:
- `JSONRotatingFileHandler`: 10MB rotation, 5 backups → `.agentweave/logs/events.jsonl`
- `HubHandler`: Forwards to Hub when HTTP transport active

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
- Hub API key format: `aw_live_{random32}`
- HttpTransport uses stdlib `urllib.request` only
- Stage paths explicitly; `git add -A` sweeps in untracked `.claude/handoffs/` scratch

## Common Tasks

### Adding a CLI Command

1. Add `cmd_<name>()` function in `cli.py`
2. Add subparser in `create_parser()`
3. Add routing branch in `main()`
4. Add tests in `tests/test_cli.py`

### Adding a Transport

1. Create class in `transport/<name>.py` extending `BaseTransport`
2. Implement all 6 abstract methods
3. Add branch in `transport/config.py`
4. Add CLI handling in `cmd_transport_setup()`

### Adding an MCP Tool

1. Add `@mcp.tool()` decorated function in `mcp/server.py` (CLI) or `hub/mcp_server.py` (Hub)
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
