# AgentWeave

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://badge.fury.io/py/agentweave-ai.svg)](https://badge.fury.io/py/agentweave-ai)

> **A collaboration framework for N AI agents — Claude, Kimi, Gemini, Codex, and more**

AgentWeave lets multiple AI agents work together on the same project through a shared protocol. Agents communicate through a local `.agentweave/` directory, a local MCP server, or the **AgentWeave Hub** — a self-hosted server with a web dashboard.

---

## Three Modes

| Mode | Setup | Best for |
|------|-------|----------|
| **Manual relay** | Zero — just install | Quick start, occasional delegation |
| **Zero-relay MCP** | `agentweave mcp setup` + 2 watchers | Autonomous loops, same machine |
| **Hub** | Docker + `agentweave transport setup --type http` | Teams, multi-machine, web dashboard |

---

## Repository Layout

```
AgentWeave/
├── src/agentweave/     CLI package (Python 3.8+, zero runtime deps) — v0.6.0
├── hub/                AgentWeave Hub server (Python 3.11+, FastAPI + Docker) — v0.2.0
│   ├── hub/            Hub Python package
│   ├── ui/             React dashboard (built into Docker image, no separate server)
│   └── Dockerfile      Multi-stage build: Node UI → Python server
├── tests/              CLI unit tests (pytest)
└── Makefile            Convenience targets for both packages
```

> **Note on Hub + UI:** The dashboard UI lives inside `hub/ui/` and is compiled into the Docker image. The Hub serves it at the same port — no separate server or CORS config needed in production. For development, `npm run dev` in `hub/ui/` proxies API calls to `localhost:8000`.

---

## Quick Start — CLI Only (Manual Relay)

### 1. Install

```bash
pip install agentweave-ai

# With MCP server (zero-relay mode)
pip install "agentweave-ai[mcp]"

# From source
git clone https://github.com/gutohuida/AgentWeave.git
cd AgentWeave
pip install -e ".[mcp]"
```

### 2. Initialize (once per project)

```bash
cd your-project/
agentweave init --project "My App" --agents claude,kimi
```

Creates `AI_CONTEXT.md` (project DNA) and `.agentweave/` with AGENTS.md, ROLES.md, and shared/context.md.

**Supported agents:** claude, kimi, gemini, codex, aider, cline, cursor, windsurf, copilot, and any name matching `^[a-zA-Z0-9_-]{1,32}$`

### 3. Fill in project context

- **`AI_CONTEXT.md`** — fill once: stack, architecture, commands, standards
- **`.agentweave/shared/context.md`** — update daily: current phase, blockers, decisions

### 4. Start working — manual relay

> "Claude, delegate the database schema design to Kimi."

Claude runs `agentweave quick` and `agentweave relay`, then shows you a prompt to paste into Kimi Code.

### 4b. Start working — zero-relay MCP

```bash
# One-time: configure MCP in all session agents
agentweave mcp setup

# Start background watchdog — monitors all agents, one process, one command
agentweave start

# Stop it later
agentweave stop
```

Restart your Claude/Kimi sessions so they pick up the MCP server. Then just prompt Claude — agents communicate autonomously.

---

## Quick Start — AgentWeave Hub

The Hub is a self-hosted server providing REST + SSE + MCP interfaces, plus a web dashboard.

### Option A — Docker (recommended, no source needed)

```bash
# 1. Download config files
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/docker-compose.yml
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/.env.example

# 2. Create your .env
cp .env.example .env

# 3. Generate a secure API key and paste into .env
python -c "import secrets; print('aw_live_' + secrets.token_hex(16))"
# Paste the output as AW_BOOTSTRAP_API_KEY in .env

# 4. Start Hub
docker compose up -d

# Hub is now running at http://localhost:8000
# Dashboard at http://localhost:8000  (auto-configured, no login needed)
```

### Option B — Build from source

```bash
git clone https://github.com/gutohuida/AgentWeave.git
cd AgentWeave/hub

cp .env.example .env
# Edit .env: set AW_BOOTSTRAP_API_KEY

docker compose up --build -d
```

### Connect the CLI to Hub

```bash
# 6. Go to your project directory
cd /path/to/your-project

# 7. Initialize the project
agentweave init --project "My App" --agents claude,kimi

# 8. Connect CLI to Hub
agentweave transport setup --type http \
  --url http://localhost:8000 \
  --api-key aw_live_<your-key> \
  --project-id proj-default

# 9. Register MCP server with all session agents (one command)
agentweave mcp setup

# 10. Start background watchdog for all agents (one command, one terminal)
agentweave start
# Stop it later with: agentweave stop
```

That's it. Restart your Claude/Kimi sessions so they pick up the new MCP server.

### Hub UI development (hot-reload)

```bash
cd hub/ui
npm install
npm run dev        # dashboard at http://localhost:5173, proxies /api → Hub
```

---

## Commands Reference

### Session

```bash
agentweave init --project "Name" --principal claude
agentweave status
agentweave summary
```

### Delegation

```bash
agentweave quick --to kimi "Task description"
agentweave relay --agent kimi
agentweave inbox --agent claude
```

### Tasks

```bash
agentweave task list
agentweave task show <task_id>
agentweave task update <task_id> --status in_progress
agentweave task update <task_id> --status completed
agentweave task update <task_id> --status approved
agentweave task update <task_id> --status revision_needed --note "Fix X"
```

### Transport

```bash
agentweave transport setup --type git                  # cross-machine via git orphan branch
agentweave transport setup --type http --url ... \
  --api-key ... --project-id ...                       # Hub transport
agentweave transport status
agentweave transport pull
agentweave transport disable
```

### Human interaction (Hub only)

```bash
agentweave reply --id <question_id> "Your answer"      # answer a question from an agent
```

---

## MCP Tools Reference

Available to agents in both local MCP mode and via Hub MCP:

| Tool | What it does |
|------|-------------|
| `send_message(from, to, subject, content)` | Send a message to another agent |
| `get_inbox(agent)` | Read unread messages |
| `mark_read(message_id)` | Archive a message after processing |
| `list_tasks(agent?)` | List active tasks |
| `get_task(task_id)` | Get full task details |
| `update_task(task_id, status)` | Update task status |
| `create_task(title, ...)` | Create and assign a new task |
| `get_status()` | Session-wide summary + task counts |
| `ask_user(from_agent, question)` | Post a question to the human (Hub only) |
| `get_answer(question_id)` | Check if the human answered (Hub only) |

---

## Task Status Lifecycle

```
pending → assigned → in_progress → completed → under_review → approved
                                             ↘ revision_needed (loops back)
                                             ↘ rejected
```

---

## Cross-Machine Collaboration

### Via Git (no server required)

```bash
agentweave transport setup --type git --cluster yourname
```

Creates an orphan branch (`agentweave/collab`) on your git remote. Messages sync through git plumbing — working tree and HEAD are never touched.

### Via Hub (recommended for teams)

Deploy the Hub once, connect all agents via HTTP transport. The web dashboard shows all messages, tasks, and human questions in real time.

---

## Safety & Quality

- **File locking** — file-based mutexes prevent race conditions when agents write simultaneously
- **Schema validation** — all data validated before saving; agent names, task statuses, and required fields enforced
- **Input sanitization** — string length limits and type coercion before any write
- **API validation** — Hub rejects invalid `status`/`priority`/`type` values with HTTP 422
- **Pagination** — all Hub list endpoints support `offset`/`limit` (default 100)
- **CORS** — configurable via `AW_CORS_ORIGINS` env var

---

## Development

```bash
# Install CLI for development
pip install -e ".[dev]"

# Or use the Makefile
make install-all    # both CLI and Hub
make test-all       # pytest for both
make lint           # ruff + mypy
make format         # black

# Run CLI tests
pytest tests/ -v

# Run Hub tests
pytest hub/tests/ -v

# Hub from source
make hub-build      # build Docker image and start
make hub-up         # start existing image
make hub-down       # stop
```

---

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| Local transport | ✅ Done | Single-machine via `.agentweave/` filesystem |
| Git transport | ✅ Done (v0.2.0) | Cross-machine via orphan branch, zero infra |
| N-agent support | ✅ Done (v0.3.0) | Multi-agent teams with ROLES.md and cluster naming |
| Local MCP server | ✅ Done (v0.4.0) | Native tool integration, zero-relay with watchdog pinger |
| HTTP transport | ✅ Done (v0.5.0) | CLI ↔ Hub via REST |
| AgentWeave Hub | ✅ Done (v0.2.0) | Self-hosted server, REST + SSE + MCP + web dashboard |
| Hub UI | ✅ Done (v0.2.0) | React dashboard — tasks, messages, human questions, agent trigger |
| Agent Trigger | ✅ Done (v0.6.0) | Trigger agents from Hub UI; watchdog executes on host (no CLIs in Docker) |
| Per-agent context templates | ✅ Done (v0.6.0) | `claude_context.md`, `kimi_context.md`, `collab_protocol.md` |
| Official hosted Hub | 🔲 Planned | Public `hub.agentweave.dev` — Supabase + Vercel + Railway |

---

## FAQ

**Q: Do I need the Hub?**
No. Manual relay and local MCP modes work with zero infra. The Hub adds a web dashboard, multi-machine support, and human question-answering via the dashboard.

**Q: Should I put the UI in a separate folder/repo?**
No. The UI (`hub/ui/`) is built into the Docker image and served by the Hub at the same port. Keeping them together avoids a second server and CORS configuration. For local dev, `npm run dev` in `hub/ui/` proxies API calls to the running Hub.

**Q: Do I need to run CLI commands during my session?**
No. After `agentweave init`, just talk to Claude. It runs all `agentweave` commands via Bash automatically.

**Q: Do the watchdog processes need to stay running?**
Yes (in local MCP mode). Run `agentweave-watch --auto-ping --agent <name>` for each agent. If they stop, messages still queue — agents just won't be auto-triggered.

**Q: Should I commit `.agentweave/`?**
Partially. Runtime state (tasks, messages, session.json, transport.json) is gitignored. AGENTS.md and README.md are committed.

**Q: Do both developers need the same git remote for git transport?**
Yes. Git transport requires a shared remote (e.g. `origin`).

---

## Links

- **GitHub:** https://github.com/gutohuida/AgentWeave
- **PyPI:** https://pypi.org/project/agentweave-ai/
- **Issues:** https://github.com/gutohuida/AgentWeave/issues
- **Roadmap:** [ROADMAP.md](ROADMAP.md)

---

MIT License
