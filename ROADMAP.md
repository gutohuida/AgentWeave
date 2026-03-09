# InterAgent Roadmap

This document records what has been built and what is planned next.
Any AI instance working in this repository should read this before proposing
new features or changes to the transport layer.

---

## What Exists Today (Phase 1 complete)

### Single-machine collaboration (original)
Claude Code and Kimi Code collaborate via a shared `.interagent/` directory.
All state is local: messages in `messages/pending/*.json`, tasks in
`tasks/active/*.json`. No external dependencies. See README.md for the
full protocol.

### Transport abstraction layer (Phase 1 complete)
Cross-machine collaboration is enabled by a pluggable transport layer.
`MessageBus` and `Watchdog` no longer talk to the filesystem directly —
they go through a `BaseTransport` interface.

**Transport selection** is automatic, based on `.interagent/transport.json`:
- No file → `LocalTransport` (default, zero behavior change)
- `"type": "git"` → `GitTransport` (orphan branch, cross-machine)
- `"type": "http"` → `HttpTransport` stub (not yet implemented)

**Key files:**
```
src/interagent/transport/
  __init__.py    re-exports get_transport(), BaseTransport
  base.py        BaseTransport ABC (6 abstract methods)
  local.py       LocalTransport — wraps existing filesystem behavior
  git.py         GitTransport — git plumbing on orphan branch
  http.py        HttpTransport stub — defines Hub API contract
  config.py      get_transport() factory — reads transport.json
```

**New CLI commands:**
```bash
interagent transport setup --type git [--remote origin] [--branch interagent/collab]
interagent transport status
interagent transport pull
interagent transport disable
```

**New constants** (in `constants.py`):
- `TRANSPORT_CONFIG_FILE` = `.interagent/transport.json`
- `GIT_COLLAB_BRANCH` = `"interagent/collab"`
- `GIT_SEEN_DIR` = `.interagent/.git_seen/` (gitignored)

---

## GitTransport — How It Works

Messages and tasks are stored as JSON files on an **orphan branch** named
`interagent/collab`. The branch shares no history with `main`.

### Why git plumbing
All git operations use low-level plumbing commands (`hash-object`, `mktree`,
`commit-tree`, `push`). The working tree and HEAD are **never touched**.
The user's current branch and uncommitted work are completely unaffected.

### File naming on the branch
```
Messages: {iso_ts}-{from}-{to}-{uuid6}.json
  e.g.    20260309T142301Z-claude-kimi-a3f2c1.json

Tasks:    {iso_ts}-task-for-{assignee}-{uuid6}.json
  e.g.    20260309T142301Z-task-for-kimi-b7d3e2.json

Task status updates: {task_id}-status-{new_status}-{iso_ts}.json
```

The recipient is encoded in the filename, so inbox filtering is a cheap
filename-only check — no file reads needed to find "messages for kimi".

### Conflict-free design
Files are **append-only and never edited**. Two machines pushing simultaneously
never produce the same filename (UUID suffix). On a push conflict (non-fast-forward),
`GitTransport._push_file()` retries up to 3 times with exponential backoff.

### Seen-set tracking
To avoid re-delivering messages, seen message IDs are stored locally in
`.interagent/.git_seen/{agent}-seen.txt`. This file is gitignored (machine-local).
`archive_message()` adds to the seen set. The watchdog does NOT add to the
seen set — it only notifies.

### Setup (one-time per developer)
```bash
# Developer A (or both):
interagent transport setup --type git --remote origin

# This:
# 1. Creates the orphan branch on the remote (if it doesn't exist)
# 2. Writes .interagent/transport.json
# 3. Both developers' interagent commands now sync via the branch
```

---

## Phase 2 — HttpTransport Implementation (planned)

`src/interagent/transport/http.py` currently raises `NotImplementedError`.
When the Hub is built (Phase 3), this stub will be implemented using
`urllib.request` (stdlib only) to call the Hub's API.

The stub already defines the expected API contract:
```
POST   {url}/api/v1/messages
GET    {url}/api/v1/messages?agent=X
PATCH  {url}/api/v1/messages/{id}/read
POST   {url}/api/v1/tasks
GET    {url}/api/v1/tasks?agent=X
PATCH  {url}/api/v1/tasks/{id}
```

---

## Phase 3 — InterAgent Hub (planned, MCP-based)

### What the Hub is
A hosted (or self-hosted) server where multiple developers connect their AI
instances. Instead of needing a shared git remote, teams connect to the Hub
and all messages/tasks flow through it.

### Key architectural decision: MCP, not REST
The Hub will be exposed as an **MCP (Model Context Protocol) server**, not
a traditional REST API. This means:

- Claude Code and Kimi Code connect to the Hub as an MCP server
- Message send/receive are **MCP tools**, not HTTP endpoints
- The CLI's `HttpTransport` will be replaced (or extended) by a
  `McpTransport` that speaks MCP protocol
- Real-time delivery via MCP's streaming capabilities (no polling needed)
- No custom HTTP client code — Claude Code's built-in MCP support handles transport

### Why MCP instead of REST
1. Claude Code and Kimi Code natively support MCP servers — no SDK needed
2. MCP tools are first-class AI capabilities; agents can use them directly
   without CLI wrappers
3. Streaming support built-in — messages arrive as events, not polled
4. Authentication, schema validation, and discovery come from the MCP spec
5. Any MCP-compatible AI (not just Claude/Kimi) can participate

### Hub capabilities (beyond what git transport can do)

| Feature | Git Transport | Hub (MCP) |
|---|---|---|
| Setup | 1 CLI command | Account + MCP server URL |
| Latency | 5–30s (git fetch) | Real-time (MCP events) |
| Web dashboard | None | Yes |
| Multi-team | 2 devs, same repo | N users, N projects |
| No git required | No | Yes |
| Persistent history | Git log | Database, queryable |
| Cross-repo | No | Yes |
| Analytics | None | Task duration, completion rates |

### Recommended tech stack for Hub server
- **Backend**: FastAPI + Python (consistent with CLI codebase)
  - Exposes an MCP server endpoint (JSON-RPC over HTTP/SSE)
  - MCP tools: `send_message`, `get_messages`, `send_task`, `get_tasks`, etc.
- **Database**: PostgreSQL (via Supabase for hosted, SQLite for self-hosted)
  - Supabase Realtime for push delivery when using WebSocket MCP transport
- **Auth**: API keys per project (format: `iaf_live_{random_32}`)
  - GitHub OAuth for the web UI
- **Frontend** (Phase 4): Next.js 14 + Tailwind CSS
- **Self-hosting**: Docker Compose

### MCP tool contract (what the Hub exposes)
```
tool: send_message    args: {from, to, subject, content, type, task_id}
tool: get_messages    args: {agent, since?}  → [{message objects}]
tool: archive_message args: {message_id}
tool: send_task       args: {title, description, assignee, assigner, priority}
tool: get_tasks       args: {agent?, status?}  → [{task objects}]
tool: update_task     args: {task_id, status?, note?}
```

### New CLI command (Phase 3)
```bash
interagent transport setup --type http \
  --url https://hub.interagent.dev \
  --api-key iaf_live_xxx \
  --project-id proj-abc123
```

### Separate repository
The Hub lives in a separate repo: `github.com/gutohuida/InterAgentHub`.
The InterAgentFramework CLI repo only adds `McpTransport` — the Hub
is entirely self-contained.

---

## Phase 4 — Hub Web UI (planned)

Next.js dashboard showing:
- Project overview (active agents, task board)
- Message threads between agents
- Task kanban / list view
- API key management
- Agent activity timeline

---

## Phase 5 — Official Hosted Hub (planned)

Public hosted instance at `hub.interagent.dev`:
- Supabase (PostgreSQL + Auth + Realtime)
- FastAPI on Railway or Render
- Next.js on Vercel
- Self-hosting via Docker Compose for private deployments

---

## Phasing Summary

```
Phase 1 (DONE):   Transport abstraction layer
                   LocalTransport (unchanged), GitTransport (new), HttpTransport (stub)
                   New CLI: interagent transport setup|status|pull|disable

Phase 2 (next):   HttpTransport implementation (urllib.request → Hub REST API)
                   interagent transport setup --type http

Phase 3 (hub):    InterAgentHub v0.1 — FastAPI MCP server + SQLite
                   McpTransport in CLI, MCP tools for send/receive
                   Self-hostable, no UI yet

Phase 4 (hub UI): Next.js dashboard — task board, message threads, agent status

Phase 5 (hosted): hub.interagent.dev — Supabase + Vercel + Railway
                   Community-hosted option for teams without infra
```

Git transport (Phase 1) handles 80% of the use case with zero infrastructure.
The Hub unlocks the rest: larger teams, UI, analytics, no-git workflows.
```
