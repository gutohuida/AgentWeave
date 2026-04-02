# CLAUDE.md

This file provides guidance to Claude Code when working on the **AgentWeave Framework** codebase itself.

## Project Context

You are working on the **AgentWeave Framework** — a multi-agent AI collaboration platform consisting of:
- **CLI** (`src/agentweave/`) — Python 3.8+, zero runtime dependencies, published as `agentweave-ai` on PyPI
- **Hub** (`hub/`) — FastAPI backend + React/Vite dashboard, self-hosted via Docker
- **Documentation** (`docs/`) — MkDocs with Material theme, deployed to GitHub Pages

Current version: **v0.15.0** (CLI + Hub v0.9.0)

## Quick Commands

### Development Setup

```bash
# CLI (editable install)
pip install -e ".[dev,mcp]"

# Verify
agentweave --help
aw --help

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
│   │   │   │   ├── AgentPromptPanel.tsx   # Chat + session selector
│   │   │   │   ├── AgentOutputPanel.tsx   # Live output logs
│   │   │   │   ├── AgentActivityTab.tsx
│   │   │   │   ├── AgentInfoTab.tsx
│   │   │   │   ├── AgentMessageSender.tsx
│   │   │   │   └── AgentTimeline.tsx
│   │   │   ├── tasks/        # TaskBoard, TaskCard
│   │   │   ├── messages/     # MessagesFeed, MessageCard, ConversationGroup
│   │   │   ├── questions/    # QuestionsPanel, AnswerForm
│   │   │   ├── logs/         # LogsView, LogLine
│   │   │   ├── activity/     # ActivityLog, EventRow
│   │   │   ├── layout/       # Sidebar, StatusBar, SetupModal
│   │   │   └── common/       # Badge, Icon, EmptyState
│   │   ├── store/            # Zustand stores (configStore)
│   │   └── hooks/            # useSSE, useCopy, useApiConfig
│   └── package.json
├── docker-compose.yml
└── Dockerfile
```

## Key Features (v0.15.0)

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
- NEVER commit `.agentweave/tasks/`, `messages/`, `agents/`, `session.json`, `transport.json`
- NEVER commit `kimichanges.md`, `kimiwork.md`
- Hub API key format: `aw_live_{random32}`
- HttpTransport uses stdlib `urllib.request` only

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
5. Use `Icon` component for Material Symbols

## When Compacting

Keep in context:
- Current task IDs being worked on
- Session mode (hierarchical/peer/review)
- Principal agent name
- Active transport type (local/git/http)
- Pending messages in `.agentweave/messages/pending/`
- Which CLI command or UI component is being modified
- Any proxy agents (minimax, glm) and their runner config

## Resources

- GitHub: https://github.com/gutohuida/AgentWeave
- PyPI: https://pypi.org/project/agentweave-ai/
- Docs: https://gutohuida.github.io/AgentWeave/
- Issues: https://github.com/gutohuida/AgentWeave/issues
