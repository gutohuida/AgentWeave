# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
File-based collaboration protocol enabling Claude Code and Kimi Code to work together through a shared `.agentweave/` directory. Zero external dependencies — pure Python stdlib. Supports single-machine (local) and cross-machine (git orphan branch) collaboration. The AgentWeave Hub (self-hosted FastAPI server) is now available in `hub/` — see ROADMAP.md.

## Tech Stack
- Python 3.8+, no external runtime dependencies
- Package manager: pip (editable install: `pip install -e .`)
- Entry points: `agentweave`, `aw` → `agentweave.cli:main`
- Watchdog entry point: `agentweave-watch` → `agentweave.watchdog:main`

## Essential Commands

```bash
# Install
pip install -e .                              # runtime only
pip install -e ".[dev]"                       # include pytest, black, ruff, mypy

# Verify
agentweave --help

# Session lifecycle
agentweave init --project "Name" --principal claude
agentweave status
agentweave summary

# Delegation workflow
agentweave quick --to kimi "task description"
agentweave relay --agent kimi                 # NOTE: flag is --agent, not --to
agentweave inbox --agent claude

# Tasks
agentweave task list
agentweave task show <task_id>
agentweave task update <task_id> --status in_progress
agentweave task update <task_id> --status completed

# Cross-machine transport (git)
agentweave transport setup --type git         # one-time setup per developer
agentweave transport status                   # show active transport
agentweave transport pull                     # force immediate fetch
agentweave transport disable                  # revert to local filesystem

# Hub — end-user install (no source code needed, pulls pre-built image)
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/docker-compose.yml
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/.env.example
cp .env.example .env   # edit AW_BOOTSTRAP_API_KEY
docker compose up -d

# Hub — build and run from source (inside hub/ directory)
docker compose up --build -d

# UI development (hot-reload, proxies /api → Hub at localhost:8000)
cd hub/ui && npm install && npm run dev       # dashboard at http://localhost:5173
cd hub/ui && npm run build                    # produces dist/ (copied into Docker image)

# Connect CLI to Hub
agentweave transport setup --type http --url http://localhost:8000 \
  --api-key aw_live_... --project-id proj-default

# Human interaction
agentweave reply --id <question_id> "Your answer"

# Template maintenance
agentweave update-template --agent claude --template-path ~/Documents/projects/template.txt
```

## Dev / Quality Commands

```bash
# Lint and format (line length 100)
ruff check src/
black src/

# Type checking
mypy src/

# Tests (tests/ directory does not yet exist — needs to be created)
pytest
```

## Architecture

```
hub/                  AgentWeave Hub server (FastAPI + SQLite + MCP)
  hub/main.py         FastAPI app factory + lifespan
  hub/db/             SQLAlchemy async models + engine (5 tables)
  hub/api/v1/         REST endpoints (messages, tasks, questions, status, events SSE)
  hub/mcp_server.py   FastMCP server (10 tools: 8 existing + ask_user + get_answer)
  docker-compose.yml  Self-hosted deployment
  pyproject.toml      Hub dependencies (FastAPI, SQLAlchemy, fastmcp, etc.)

src/agentweave/
  cli.py          All CLI commands (argparse). To add a command: add cmd_*, add subparser in
                  create_parser(), add routing branch in main()
  session.py      Session lifecycle (create, load, save, add_task, complete_task)
  task.py         Task CRUD; Task.load() validates task_id with ^[a-zA-Z0-9_-]+$
  messaging.py    MessageBus (send, get_inbox, mark_read) — routes through transport layer
  locking.py      File-based mutex; prefer `with lock("name"):` over raw acquire/release
  validator.py    validate_task/message/session + sanitize_task_data — run before every save
  watchdog.py     Polls for new files; transport-aware (local glob or remote fetch)
  constants.py    All valid values and directory Path constants — source of truth
  utils.py        load_json, save_json, generate_id, now_iso, print_* helpers
  templates/      Markdown prompt templates; load via get_template("name") from
                  templates/__init__.py — templates are .md files in that directory
  transport/      Pluggable transport layer (see below)

.agentweave/      Runtime state — gitignored except README.md and AGENTS.md
AI_CONTEXT.md     Versioned best-practices template created by `agentweave init` at project
                  root; basis for generating CLAUDE.md via `agentweave update-template`
ROADMAP.md        Full architecture plan: transport layer, git transport, planned Hub (MCP)
```

## Transport Layer

All message and task I/O goes through `BaseTransport`. Selection is automatic:

```
No transport.json  →  LocalTransport   (default, unchanged single-machine behavior)
type: "git"        →  GitTransport     (orphan branch agentweave/collab, cross-machine)
type: "http"       →  HttpTransport    (AgentWeave Hub — not yet implemented, see ROADMAP.md)
```

```
src/agentweave/transport/
  base.py     BaseTransport ABC — 6 abstract methods all transports must implement
  local.py    LocalTransport — wraps existing .agentweave/ filesystem behavior
  git.py      GitTransport — git plumbing only (hash-object, mktree, commit-tree, push)
  http.py     HttpTransport stub — defines Hub API contract, raises NotImplementedError
  config.py   get_transport() factory — reads .agentweave/transport.json
  __init__.py re-exports get_transport(), BaseTransport, all transport classes
```

**GitTransport design principles:**
- Uses only git plumbing — never touches working tree or HEAD
- Files on the branch are append-only; UUID suffix prevents conflicts between concurrent pushes
- Message filename: `{iso_ts}-{from}-{to}-{uuid6}.json` (recipient encoded in name)
- Seen-set in `.agentweave/.git_seen/{agent}-seen.txt` tracks archived message IDs (gitignored)
- Watchdog for git transport tracks known remote filenames in memory (does NOT add to seen set)

**Adding a new transport:** Create a class in `transport/` that extends `BaseTransport`,
implement all 6 abstract methods, add a `elif transport_type == "..."` branch in `config.py`,
and add CLI handling in `cmd_transport_setup()`.

## Task Status Lifecycle

```
pending → assigned → in_progress → completed → under_review → approved
                                             ↘ needs_revision (loops back)
                                             ↘ rejected
```

Valid statuses (from `constants.py`): `pending`, `assigned`, `in_progress`, `completed`, `under_review`, `revision_needed`, `approved`, `rejected`

## Critical Rules

- Agent names are validated by `AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")` in `constants.py`. Any name matching this regex is accepted. `KNOWN_AGENTS` is a documentation/suggestion list only, not a validation gate.
- `VALID_MODES = ["hierarchical", "peer", "review"]`
- ALL saves must pass through `validator.py` sanitize functions first
- ALL task file operations that modify state must use `locking.py` context manager (`with lock("name"):`)
- Templates use `get_template("name")` from `templates/__init__.py` — never hardcode template strings in `cli.py`
- `is_locked()` is read-only — it must never delete files (only `acquire_lock()` cleans stale locks)
- NEVER commit `.agentweave/tasks/`, `messages/`, `agents/`, `session.json` (already gitignored)
- NEVER commit `.agentweave/transport.json` or `.agentweave/.git_seen/` (gitignored, machine-local)
- `kimichanges.md` and `kimiwork.md` are gitignored working files — never commit them
- The `relay` subcommand flag is `--agent`, not `--to` — never write `relay --to`
- Hub API key format is `aw_live_{random32}` — never commit keys
- Hub is in `hub/` subdirectory; CLI is in `src/agentweave/` — two separate packages
- HttpTransport uses stdlib `urllib.request` only — no new CLI dependencies

## When Compacting

Keep in context: current task IDs being worked on, session mode, which agent is principal, active transport type, any pending messages in `.agentweave/messages/pending/`, which CLI command is being added/modified.
