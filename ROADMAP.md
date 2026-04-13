# AgentWeave Roadmap

This document records what has been built and what is planned next.
Any AI instance working in this repository should read this before proposing
new features or changes to the transport layer.

---

## What Exists Today

### Phase 1 — Transport abstraction layer (DONE)

Single-machine collaboration via `.agentweave/` filesystem, plus pluggable
cross-machine transports.

**Transport selection** is automatic, based on `.agentweave/transport.json`:
- No file → `LocalTransport` (default, zero behavior change)
- `"type": "git"` → `GitTransport` (orphan branch, cross-machine)
- `"type": "http"` → `HttpTransport` (Hub REST API)

**Key files:**
```
src/agentweave/transport/
  __init__.py    re-exports get_transport(), BaseTransport
  base.py        BaseTransport ABC (6 abstract methods)
  local.py       LocalTransport — wraps existing filesystem behavior
  git.py         GitTransport — git plumbing on orphan branch
  http.py        HttpTransport — stdlib urllib.request → Hub REST API
  config.py      get_transport() factory — reads transport.json
```

**CLI commands:**
```bash
agentweave transport setup --type git [--remote origin] [--branch agentweave/collab]
agentweave transport setup --type http --url <url> --api-key <key> --project-id <id>
agentweave transport status
agentweave transport pull
agentweave transport disable
```

---

### GitTransport — How It Works

Messages and tasks are stored as JSON files on an **orphan branch** named
`agentweave/collab`. The branch shares no history with `main`.

All git operations use low-level plumbing commands (`hash-object`, `mktree`,
`commit-tree`, `push`). The working tree and HEAD are **never touched**.

**File naming on the branch:**
```
Messages: {iso_ts}-{from}-{to}-{uuid6}.json
Tasks:    {iso_ts}-task-for-{assignee}-{uuid6}.json
Task status updates: {task_id}-status-{new_status}-{iso_ts}.json
```

Files are **append-only and never edited**. Two machines pushing simultaneously
never produce the same filename (UUID suffix). On push conflict, `_push_file()`
retries up to 3 times with exponential backoff.

---

### Phase 2 — HttpTransport (DONE, v0.5.0)

`src/agentweave/transport/http.py` is fully implemented using `urllib.request`
(stdlib only — no new CLI dependencies). It calls the Hub REST API.

---

### Phase 3 — AgentWeave Hub v0.1.0+ (DONE)

Self-hosted FastAPI server with SQLite, REST + SSE + MCP interfaces.

```
hub/
  hub/main.py           FastAPI app factory + lifespan
  hub/db/               SQLAlchemy async models + engine
  hub/api/v1/           REST endpoints (messages, tasks, questions, status, events SSE, agents, logs, jobs, setup)
  hub/mcp_server.py     FastMCP server (15+ tools)
  docker-compose.yml    Self-hosted deployment
```

**MCP tools:**
```
send_message, get_inbox, mark_read, list_tasks, get_task,
update_task, create_task, get_status, ask_user, get_answer,
register_session, get_agent_config, list_agents,
create_job, list_jobs, get_job, toggle_job, delete_job, run_job
```

---

### Phase 4 — Hub Web UI + Agent Trigger (DONE, v0.2.0)

React dashboard built into the Docker image. No separate server or CORS config.

**New in v0.2.0+:**

| Feature | Description |
|---------|-------------|
| **Agent Trigger** | `POST /api/v1/agent/trigger` — triggers an agent without CLIs in Docker; creates a message the host-side watchdog picks up and executes on the host machine |
| **Session listing** | `GET /api/v1/agent/sessions/{agent}` — lists available CLI sessions for an agent |
| **Agent Configurator UI** | Add/remove configured agents; reads from `session.json` or manual list *(later replaced by session sync)* |
| **Agent Message Sender UI** | Compose and send prompts to agents from the dashboard, with session resume support |
| **Agent Chat** | Per-session chat history with live updates |
| **Agent configure API** | `POST/DELETE/GET /api/v1/agents/configure` per project |
| **UI refresh** | Redesigned all dashboard components, new Tailwind config, dark theme |
| **Dockerfile.dev** | Hot-reload development workflow for Hub |

**Agent Trigger flow:**
```
1. UI calls POST /api/v1/agent/trigger
2. Hub creates a message in the database
3. Watchdog (on host) polls for messages, sees the new one
4. Watchdog executes the CLI on the host machine
5. Output streams back to Hub via HTTP transport
```

This design means the Hub runs in Docker while CLIs (claude, kimi, etc.) run
on the host — no AI tooling required inside the container.

---

### Phase 5 — Per-Agent Context Templates (DONE, v0.6.0)

Agent-specific Markdown prompt templates generated via `agentweave update-template`.

**New templates:**
- `claude_context.md` — session start checklist and role rules for Claude
- `kimi_context.md` — same, for Kimi Code
- `collab_protocol.md` — cross-agent collaboration protocol

**Removed:**
- `agents_guide.md` — replaced by per-agent templates

---

### Phase 6 — Yolo Mode + Session Sync (DONE, v0.10.0)

- **Yolo mode** — per-agent flag to suppress confirmation prompts
- **Session sync to Hub** — `session.json` auto-pushed to Hub; agents appear in dashboard without manual configuration

---

### Phase 7 — Claude-Proxy Agents (DONE, v0.12.0)

Run MiniMax, GLM, and any OpenAI-compatible provider through the Claude CLI by injecting `ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY`.

- Built-in provider registry (minimax, glm)
- `agentweave switch`, `agentweave run`, `agentweave agent configure`
- Per-agent session tracking

---

### Phase 8 — Multi-Role Support (DONE, v0.15.0)

Agents can have multiple roles simultaneously.

- `agentweave roles` CLI commands
- Role guide auto-copy to `.agentweave/roles/{role}.md`
- Hub sync for role changes

---

### Phase 9 — AgentWeave Skills + Session-Based Chat (DONE, v0.16.0-0.17.0)

- 8 collaboration skills (`aw-delegate`, `aw-status`, `aw-done`, etc.)
- AW-Spec workflow skills (`aw-spec-explore`, `aw-spec-propose`, `aw-spec-apply`, `aw-spec-archive`)
- Per-session chat history in Hub UI
- Mission Control dashboard

---

### Phase 10 — AI Jobs (DONE, v0.20.1)

Scheduled recurring agent tasks with cron expressions.

- `agentweave jobs` CLI
- Hub scheduler with run history
- MCP tools for job management

---

### Phase 11 — Pilot Mode (DONE, v0.21.0)

Manual session management for long-running agents.

- Pilot flag per agent
- Session registration (`agentweave session register`)
- Kimi agent-file auto-generation
- Dashboard pilot badges

---

### Phase 12 — Declarative Configuration (DONE, v0.23.0)

Single YAML-based project configuration with `agentweave activate`.

- `agentweave.yml` — agents, hub, jobs, roles
- `agentweave activate` — idempotent apply
- Auto transport setup via `/api/v1/setup/token`
- Migration path from existing `session.json`

---

## Phasing Summary

```
Phase 1 (DONE):   Transport abstraction (LocalTransport, GitTransport, HttpTransport)
Phase 2 (DONE):   HttpTransport implementation (urllib.request → Hub REST API)
Phase 3 (DONE):   AgentWeave Hub — FastAPI + SQLite + MCP server
Phase 4 (DONE):   Hub Web UI — task board, messages, agent trigger, chat
Phase 5 (DONE):   Per-agent context templates (claude, kimi, collab_protocol)
Phase 6 (DONE):   Yolo mode + Session sync to Hub
Phase 7 (DONE):   Claude-proxy agents (minimax, glm, custom providers)
Phase 8 (DONE):   Multi-role support
Phase 9 (DONE):   AgentWeave skills + AW-Spec workflow + session chat
Phase 10 (DONE):  AI Jobs — scheduled recurring tasks
Phase 11 (DONE):  Pilot Mode — manual session management
Phase 12 (DONE):  Declarative configuration (agentweave.yml + activate)

Phase 13 (next):  Official hosted Hub at hub.agentweave.dev
                   Supabase (PostgreSQL + Auth + Realtime) + Vercel + Railway
                   Community-hosted option for teams without infra
```

Git transport handles 80% of the use case with zero infrastructure.
The Hub unlocks the rest: larger teams, web dashboard, human Q&A, agent triggering.
