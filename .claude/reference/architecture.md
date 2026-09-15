# Architecture reference

Moved out of `CLAUDE.md` on 2026-09-15 so it is read when needed rather than paid for on every
request. The trees are orientation, not an inventory — list the directory when it matters, since
they drift. The rules that constrain changes stay in `CLAUDE.md` and in `.claude/rules/`.

## CLI (`src/agentweave/`)

The CLI is **not** a collaboration surface. It does only what cannot be done from inside the app:
start it, diagnose why it will not start, stop it, reset it. Five `cmd_*` functions survive, down
from 56 — see `openspec/explorations/2026-08-02-product-direction.md` for why, before adding a sixth.

```
src/agentweave/
├── cli.py              # The 5 surviving commands: status, doctor, stop, hub_start, reset.
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

**Logging** — Python `logging` stdlib, set up in `logging_handlers.py`: `JSONRotatingFileHandler`
(10MB rotation, 5 backups → `.agentweave/logs/events.jsonl`, *inside a project, never at this
repo's root*) and `HubHandler` (forwards to the Hub). Env vars: `AW_LOG_LEVEL` (default WARNING),
`AW_LOG_FILE`.

## Hub (`hub/`)

```
hub/
├── hub/                      # Python package
│   ├── main.py               # FastAPI app factory + lifespan
│   ├── mcp_server.py         # Hub-side MCP server (26 @mcp.tool(), 25 agent-callable —
│   │                         # approve_tool_call is a harness endpoint, not a capability)
│   ├── data/charters/        # Starter charter seed documents + manifest
│   ├── db/                   # SQLAlchemy async models and migrations (models.py, engine.py)
│   ├── api/v1/               # REST endpoints: agents, runners, charters, messages, tasks,
│   │                         # questions, events (SSE), logs, agent_chat, agent_trigger, session_sync
│   └── schemas/              # Pydantic schemas
├── ui/                       # React dashboard
│   └── src/                  # App.tsx, api/ (React Query hooks), components/<category>/,
│                             # store/ (Zustand), hooks/ (useSSE, useCopy)
├── docker-compose.yml
└── Dockerfile
```

### Runner, Agent, and Charter separation

The Hub owns three independent project-scoped concepts:

- runners describe reusable execution capability (`claude`/`codex`, model, and flags);
- agents are addressable roster identities bound to at most one runner and one charter;
- charters are editable markdown behavior contracts injected into canonical turn context.

Fresh projects seed default runners and the starter charters declared in
`hub/hub/data/charters/charters.json` (9 today). Operators manage and bind them through the Hub UI.
The former CLI multi-role subsystem, fixed enum, role files, and role-derived API/UI fields no
longer exist and must not be recreated.

A runner is a Runner record in the Hub — a CLI (`claude`, `codex`, …), a model, and flags.
`hub/hub/runner_commands.py` turns one into a spawn. Claude and Codex are the two wired to a real
spawn path today; the rest are refused with a stated 501 rather than silently mishandled.

### Operator-in-the-loop

An agent can stop and involve the operator rather than guess:

- **Permissions** — the composer's Permissions pill sets the run's posture. `manual` ("Ask me")
  routes Claude through `--permission-prompt-tool` and Codex through
  `codex_appserver.decide_approval`, producing a card the operator answers.
- **Questions** — `ask_user` takes 1–4 structured questions, blocks, and returns the answers. The
  operator steps through them above the composer.

How long a run waits is per-agent (`Agent.permission_timeout_seconds`,
`Agent.question_timeout_seconds`), carried to the spawned tool process as `AW_DECISION_TIMEOUT` and
`AW_QUESTION_TIMEOUT`. (The no-backstop rule is in `CLAUDE.md`.)
