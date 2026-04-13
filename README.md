# AgentWeave

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://badge.fury.io/py/agentweave-ai.svg)](https://badge.fury.io/py/agentweave-ai)

> **A collaboration framework for N AI agents — Claude, Kimi, Gemini, Codex, Minimax, GLM, and more**
>
> 📖 [Documentation](https://gutohuida.github.io/AgentWeave/)

AgentWeave lets multiple AI agents work together on the same project through a shared protocol. The **AgentWeave Hub** is a self-hosted server with a web dashboard — the recommended way to run it.

---

## Quick Start — 3 Commands

The Hub provides a web dashboard, REST + SSE + MCP interfaces, and real-time visibility into agent activity.

### Prerequisites

- Python 3.8+ and pip
- Docker and Docker Compose

### Step 1 — Start the Hub

```bash
agentweave hub start
```

This downloads the configuration, starts the Hub, and fetches the API key automatically. The dashboard is now at **http://localhost:8000**.

---

### Step 2 — Initialize your project

```bash
cd /path/to/your-project
agentweave init --project "My App"
```

This creates:
- `agentweave.yml` — project configuration (edit to add/remove agents)
- `.agentweave/` — shared context, roles, and protocol files
- `CLAUDE.md` / `AGENTS.md` — agent context files

---

### Step 3 — Activate

```bash
agentweave activate
```

This connects to the Hub, registers agents, sets up MCP, and starts the watchdog. Done!

---

Start your Claude / Kimi sessions in the project directory — they auto-read their context files. Agents now communicate through the Hub and you monitor everything in the dashboard.

### Daily Commands

```bash
agentweave status          # Check session status
agentweave hub stop        # Stop the Hub
agentweave stop            # Stop the watchdog
```

---

## What the Dashboard Shows

Open **http://localhost:8000** to see:

- **Mission Control** — centralized overview of session status, agent states, and recent activity
- **Tasks board** — all tasks with status, priority, assignee, requirements, acceptance criteria, and deliverables (click any card to expand)
- **Messages feed** — inter-agent messages with expand-to-read for long content; message type and linked task shown inline
- **Human questions** — questions agents have asked you; answer directly in the dashboard
- **AI Jobs** — scheduled recurring tasks with cron expressions, run history, and enable/disable controls
- **Agent activity** — live event stream and per-agent output log
- **Agent cards** — connected agents auto-discovered from your session; shows role, yolo mode, pilot status, and per-agent chat history

---

## Configuration — .env reference

| Variable | Default | Description |
|----------|---------|-------------|
| `AW_BOOTSTRAP_API_KEY` | *(required)* | API key auto-created on first start (`aw_live_…`) |
| `AW_BOOTSTRAP_PROJECT_ID` | `proj-default` | Default project ID |
| `AW_BOOTSTRAP_PROJECT_NAME` | `Default Project` | Display name for the default project |
| `AW_PORT` | `8000` | Port the Hub listens on |
| `AW_CORS_ORIGINS` | *(empty)* | Comma-separated allowed origins for CORS (leave empty in production) |
| `DATABASE_URL` | `sqlite+aiosqlite:///data/agentweave.db` | SQLite path inside the container |

Data persists in a Docker volume (`hub-data`) — no manual backup needed for local use.

---

## Alternative Modes

| Mode | Setup | Best for |
|------|-------|----------|
| **Hub** | `agentweave hub start` + `agentweave activate` | Teams, multi-machine, web dashboard *(recommended)* |
| **Zero-relay MCP** | `agentweave activate` (no Hub) | Autonomous loops, same machine |
| **Manual relay** | `agentweave init` only | Quick one-off delegation |

### Zero-relay MCP (no Hub)

Skip the Hub steps and activate locally:

```bash
pip install "agentweave-ai[mcp]"
cd your-project/
agentweave init --project "My App"
agentweave activate    # Sets up MCP and watchdog locally
```

### Manual relay (simplest possible)

```bash
pip install agentweave-ai
cd your-project/
agentweave init --project "My App"
# Use agentweave quick + relay to manually hand off work between agents
```

---

## Claude-Proxy Agents (Minimax, GLM, and any OpenAI-compatible provider)

Some models — like **MiniMax** and **Zhipu GLM** — don't have a native CLI. AgentWeave runs them through the Claude Code CLI by overriding two environment variables:

```
ANTHROPIC_BASE_URL  →  the provider's OpenAI-compatible endpoint
ANTHROPIC_API_KEY   →  the provider's API key (resolved from your shell at runtime)
```

This is called a **`claude_proxy` runner**. AgentWeave tracks a separate Claude resume session ID per proxy agent so each one maintains its own conversation history.

### Setup

Add to `agentweave.yml`:

```yaml
agents:
  claude:
    runner: claude
  
  minimax:           # Built-in defaults for minimax/glm
    runner: claude_proxy
    env:
      - MINIMAX_API_KEY
    yolo: true
  
  mymodel:           # Custom provider
    runner: claude_proxy
    model: custom-model-name
    env:
      - MY_MODEL_API_KEY
```

Then run `agentweave activate` to apply.

### Running a proxy agent

```bash
# Option A — switch env vars in your current shell, then run Claude manually
export MINIMAX_API_KEY=<your-key>
eval $(agentweave switch minimax)          # exports ANTHROPIC_BASE_URL + ANTHROPIC_API_KEY
claude --resume <session-id> -p "..."

# Option B — let AgentWeave handle it (sets env + launches Claude with relay prompt)
export MINIMAX_API_KEY=<your-key>
agentweave run --agent minimax

# Option C — from relay (shows switching instructions, or auto-runs with --run)
agentweave relay --agent minimax           # shows copy-paste prompt + switching instructions
agentweave relay --agent minimax --run     # combined: sets env + launches Claude
```

### Session continuity

AgentWeave tracks the Claude session ID per proxy agent so `--resume` is used automatically on subsequent runs. To register a session ID manually (e.g. from `claude --list`):

```bash
agentweave agent set-session minimax <session-id>
```

**Security note:** API keys are never stored in `session.json`. Only the env var *name* is stored (e.g. `MINIMAX_API_KEY`). The actual value is resolved from your shell at runtime.

### Built-in provider registry

| Agent | Base URL | Env var |
|-------|----------|---------|
| `minimax` | `https://api.minimax.chat/v1` | `MINIMAX_API_KEY` |
| `glm` | `https://open.bigmodel.cn/api/paas/v4` | `ZHIPU_API_KEY` |

---

## Cross-Machine Collaboration

### Via Git (no server required)

```bash
agentweave transport setup --type git --cluster yourname
```

Creates an orphan branch (`agentweave/collab`) on your git remote. Messages sync through git plumbing — working tree and HEAD are never touched. Both developers need access to the same remote.

### Via Hub (recommended for teams)

Deploy the Hub once, connect all agents via HTTP transport. The dashboard shows all messages, tasks, and human questions in real time.

---

## Commands Reference

### Session

```bash
agentweave init --project "Name" --agents claude,kimi
agentweave status
agentweave summary
agentweave checkpoint --agent claude --reason pre_handoff   # save context before handoff
```

### Delegation

```bash
agentweave quick --to kimi "Task description"
agentweave relay --agent kimi
agentweave relay --agent minimax --run     # auto-run for claude_proxy agents
agentweave inbox --agent claude
```

### Agent runner (claude_proxy setup)

```bash
agentweave agent configure minimax                      # use built-in defaults
agentweave agent configure glm                          # use built-in defaults
agentweave agent configure mymodel \                    # custom OpenAI-compatible provider
  --runner claude_proxy \
  --base-url https://api.example.com/v1 \
  --api-key-var MY_MODEL_API_KEY
agentweave agent set-session minimax <session-id>       # register Claude resume ID manually
agentweave agent set-model minimax <model-name>         # update model for proxy agent

agentweave switch minimax        # output eval-able export commands
agentweave run --agent minimax   # set env vars + launch Claude with relay prompt
```

### Pilot Mode (manual session control)

```bash
agentweave agent configure kimi --pilot                 # enable pilot mode
agentweave session register --agent kimi --session <id> # register session ID
```

Pilot mode disables auto-triggering for an agent, giving you manual control over when sessions start and resume. Useful for Kimi Code CLI and long-running sessions.

### AI Jobs (scheduled tasks)

```bash
# Create a daily recurring job
agentweave jobs create --name "Daily Report" --agent claude \
  --message "Generate summary of yesterday's commits" --cron "0 9 * * 1-5"

# Manage jobs
agentweave jobs list                    # list all scheduled jobs
agentweave jobs get <job_id>            # view job details and run history
agentweave jobs pause <job_id>          # disable a job
agentweave jobs resume <job_id>         # re-enable a job
agentweave jobs run <job_id>            # trigger immediately
agentweave jobs delete <job_id>         # remove a job
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
agentweave transport setup --type http --url ... --api-key ... --project-id ...
agentweave transport setup --type git --cluster yourname
agentweave transport status
agentweave transport pull
agentweave transport disable
```

### Yolo mode

```bash
agentweave yolo --agent claude --enable    # allow agent to act without confirmations
agentweave yolo --agent claude --disable   # re-enable confirmation prompts
```

### Human interaction (Hub only)

```bash
agentweave reply --id <question_id> "Your answer"
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
| `create_job(name, agent, message, cron)` | Create a scheduled recurring job (Hub only) |
| `list_jobs(agent?)` | List scheduled jobs (Hub only) |
| `run_job(job_id)` | Trigger a job immediately (Hub only) |
| `register_session(agent, session_id)` | Register a pilot agent session |

---

## Task Status Lifecycle

```
pending → assigned → in_progress → completed → under_review → approved
                                             ↘ revision_needed (loops back)
                                             ↘ rejected
```

---

## Build from Source

```bash
git clone https://github.com/gutohuida/AgentWeave.git
cd AgentWeave/hub

cp .env.example .env
# Edit .env: set AW_BOOTSTRAP_API_KEY

docker compose up --build -d
```

### Hub UI development (hot-reload)

```bash
cd hub/ui
npm install
npm run dev      # dashboard at http://localhost:5173, proxies /api → Hub at localhost:8000
```

---

## Repository Layout

```
AgentWeave/
├── src/agentweave/     CLI package (Python 3.8+, zero runtime deps) — v0.23.0
├── hub/                AgentWeave Hub server (Python 3.11+, FastAPI + Docker) — v0.19.0
│   ├── hub/            Hub Python package
│   ├── ui/             React dashboard (built into Docker image, no separate server)
│   └── Dockerfile      Multi-stage build: Node UI → Python server
├── docs/               Additional documentation
├── tests/              CLI unit tests (pytest)
└── Makefile            Convenience targets for both packages
```

---

## Development

```bash
# CLI
pip install -e ".[dev]"
ruff check src/
black src/
mypy src/
pytest tests/ -v

# Hub
cd hub
pip install -e ".[dev]"
make ui-build    # rebuild React UI
pytest tests/ -v

# Both
make install-all
make test-all
make lint
```

---

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| Local transport | ✅ Done | Single-machine via `.agentweave/` filesystem |
| Git transport | ✅ Done (v0.2.0) | Cross-machine via orphan branch, zero infra |
| N-agent support | ✅ Done (v0.3.0) | Multi-agent teams with roles.json and cluster naming |
| Local MCP server | ✅ Done (v0.4.0) | Native tool integration, zero-relay with watchdog pinger |
| HTTP transport | ✅ Done (v0.5.0) | CLI ↔ Hub via REST |
| AgentWeave Hub | ✅ Done (v0.2.0) | Self-hosted server, REST + SSE + MCP + web dashboard |
| Hub UI | ✅ Done (v0.2.1) | React dashboard — expandable tasks/messages, agent trigger, configurator |
| Per-agent context templates | ✅ Done (v0.6.0) | `claude_context.md`, `kimi_context.md`, `collab_protocol.md` |
| Session sync to Hub | ✅ Done (v0.10.0) | Watchdog pushes session.json to Hub on startup; agents auto-appear in dashboard |
| Yolo mode | ✅ Done (v0.10.0) | Per-agent flag to suppress confirmation prompts for autonomous loops |
| Claude-proxy agents | ✅ Done (v0.12.0) | Run Minimax, GLM, and any OpenAI-compatible provider via Claude CLI proxy |
| Multi-role support | ✅ Done (v0.15.0) | Multiple roles per agent with `agentweave roles` CLI and Hub sync |
| AI Jobs | ✅ Done (v0.20.1) | Scheduled recurring agent tasks with cron expressions |
| Pilot Mode | ✅ Done (v0.21.0) | Manual session management for Kimi and proxy agents |
| Official hosted Hub | 🔲 Planned | Public `hub.agentweave.dev` — Supabase + Vercel + Railway |

---

## FAQ

**Q: Do I need the Hub?**
No. Manual relay and local MCP modes work with zero infra. The Hub adds a web dashboard, multi-machine support, and human question-answering.

**Q: Should I put the UI in a separate folder/repo?**
No. The UI (`hub/ui/`) is built into the Docker image and served by the Hub at the same port. No second server or CORS config needed in production.

**Q: Do I need to run CLI commands during my session?**
No. After `agentweave init`, just talk to Claude. It runs all `agentweave` commands via Bash automatically.

**Q: Do the watchdog processes need to stay running?**
Yes (in local MCP mode or Hub mode). Run `agentweave start` once. If they stop, messages still queue — agents just won't be auto-triggered.

**Q: Should I commit `.agentweave/`?**
Partially. Runtime state (tasks, messages, session.json, transport.json) is gitignored. AGENTS.md and README.md are committed.

**Q: Do both developers need the same git remote for git transport?**
Yes. Git transport requires a shared remote (e.g. `origin`).

**Q: How do I use Minimax or GLM — they don't have a CLI?**
Use `agentweave agent configure minimax` (or `glm`) to set them up as `claude_proxy` agents. AgentWeave runs them through the Claude CLI with overridden env vars (`ANTHROPIC_BASE_URL` + `ANTHROPIC_API_KEY`). Export your provider key, then run `agentweave run --agent minimax`. See the [Claude-Proxy Agents](#claude-proxy-agents-minimax-glm-and-any-openai-compatible-provider) section above.

**Q: Can I use any OpenAI-compatible provider as an agent?**
Yes. Use `agentweave agent configure <name> --runner claude_proxy --base-url <url> --api-key-var <VAR>`. The Claude CLI will proxy requests to that endpoint using your existing API key env var.

---

## Links

- **GitHub:** https://github.com/gutohuida/AgentWeave
- **PyPI:** https://pypi.org/project/agentweave-ai/
- **Issues:** https://github.com/gutohuida/AgentWeave/issues
- **Roadmap:** [ROADMAP.md](ROADMAP.md)

---

MIT License
