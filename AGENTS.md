# AgentWeave Framework - Agent Guide

> This file provides essential information for AI coding agents working on the AgentWeave Framework codebase.

## Project Overview

**AgentWeave** is a multi-agent AI collaboration framework that enables multiple AI agents (Claude, Kimi, Gemini, Codex, and more) to work together on the same project. Agents communicate through:

1. **A shared `.agentweave/` directory** (filesystem-based protocol)
2. **A local MCP server** (for native tool integration)
3. **AgentWeave Hub** (self-hosted FastAPI server with web dashboard)

The framework supports three modes:
- **Manual relay mode**: Zero dependencies, you paste relay prompts between agents
- **Zero-relay MCP mode**: Agents communicate autonomously via MCP tools + watchdog daemon
- **Hub mode**: Multi-machine collaboration via self-hosted server with web UI

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.8+ (zero runtime dependencies for CLI) |
| Package Manager | pip |
| Build System | setuptools (PEP 517) |
| Linting | ruff, black |
| Type Checking | mypy |
| Testing | pytest |
| MCP Server | fastmcp (optional dependency) |
| Hub Backend | FastAPI + SQLAlchemy + SQLite/PostgreSQL |
| Hub Frontend | React + TypeScript + Vite |

## Repository Layout

```
AgentWeave/
├── src/agentweave/              # CLI package (Python 3.8+, zero runtime deps) — v0.5.0
│   ├── __init__.py              # Package exports and version
│   ├── cli.py                   # All CLI commands (argparse) — main entry point
│   ├── session.py               # Session lifecycle management
│   ├── task.py                  # Task CRUD operations
│   ├── messaging.py             # MessageBus for agent communication
│   ├── locking.py               # File-based mutex for concurrency
│   ├── validator.py             # JSON schema validation
│   ├── watchdog.py              # File monitoring daemon with auto-ping
│   ├── eventlog.py              # Structured event logging
│   ├── constants.py             # All constants and valid values
│   ├── utils.py                 # Utility functions
│   ├── templates/               # Markdown prompt templates
│   │   ├── __init__.py          # Template loader (get_template())
│   │   ├── agents_guide.md      # Collaboration guide template
│   │   ├── ai_context.md        # AI context template
│   │   ├── roles_template.md    # Roles assignment template
│   │   └── ...
│   ├── transport/               # Pluggable transport layer
│   │   ├── base.py              # BaseTransport ABC (6 abstract methods)
│   │   ├── local.py             # Local filesystem transport
│   │   ├── git.py               # Git orphan branch transport
│   │   ├── http.py              # HTTP/REST transport for Hub
│   │   └── config.py            # Transport factory (get_transport())
│   └── mcp/                     # MCP server implementation
│       └── server.py            # FastMCP-based MCP server
├── hub/                         # AgentWeave Hub server (FastAPI + React)
│   ├── hub/                     # Hub Python package
│   │   ├── main.py              # FastAPI app factory
│   │   ├── mcp_server.py        # Hub-side MCP server
│   │   ├── api/v1/              # REST API endpoints
│   │   ├── db/                  # SQLAlchemy models and engine
│   │   └── ...
│   ├── ui/                      # React dashboard (built into Docker image)
│   └── docker-compose.yml       # Self-hosted deployment
├── tests/                       # CLI unit tests (pytest)
│   ├── test_session.py
│   ├── test_task.py
│   ├── test_messaging.py
│   ├── test_validator.py
│   ├── test_locking.py
│   └── ...
├── pyproject.toml               # Package configuration
├── Makefile                     # Convenience targets for CLI and Hub
└── README.md                    # User documentation
```

## Build and Development Commands

### Installation

```bash
# Development install (editable) — CLI only
pip install -e ".[dev]"

# With MCP support
pip install -e ".[mcp]"

# With all extras
pip install -e ".[all]"

# Install both CLI and Hub
make install-all
```

### Code Quality

```bash
# Linting (line length: 100)
ruff check src/

# Formatting
black src/ hub/hub/

# Type checking
mypy src/

# Run all linting
make lint
make format
```

### Testing

```bash
# Run CLI tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=agentweave --cov-report=term-missing

# Run Hub tests
pytest hub/tests/ -v

# Run all tests
make test-all
```

### CLI Verification

```bash
# Verify installation
agentweave --help
aw --help                    # alias
agentweave-watch --help      # watchdog
agentweave-mcp               # MCP server (stdio)
```

### Hub (Docker)

```bash
# Build and start Hub
make hub-build

# Start existing image
make hub-up

# Stop Hub
make hub-down

# UI development (hot-reload)
cd hub/ui && npm install && npm run dev  # dashboard at http://localhost:5173
```

## Key Architectural Concepts

### 1. Session Management

Sessions are stored in `.agentweave/session.json`:

```python
from agentweave import Session

session = Session.create(
    name="My Project",
    principal="claude",
    mode="hierarchical",  # or "peer", "review"
    agents=["claude", "kimi", "gemini"]
)
session.save()
```

**Session modes:**
- `hierarchical`: Principal assigns work, delegates execute
- `peer`: Agents can assign tasks to each other
- `review`: Review-focused workflow

**Agent name validation:** Use `AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")` from `constants.py`. Any name matching this regex is accepted.

### 2. Task Lifecycle

Valid statuses (defined in `constants.py`):

```
pending → assigned → in_progress → completed → under_review → approved
                                             ↘ revision_needed (loops back)
                                             ↘ rejected
```

Task operations:
```python
from agentweave import Task

task = Task.create(
    title="Implement feature",
    description="Detailed description",
    assignee="kimi",
    assigner="claude",
    priority="high"
)
task.save()
task.update(status="in_progress")
task.move_to_completed()  # When approved/completed
```

### 3. Messaging System

Messages are routed through the transport layer:

```python
from agentweave import Message, MessageBus

msg = Message.create(
    sender="claude",
    recipient="kimi",
    subject="Task assignment",
    content="Please implement...",
    message_type="delegation",
    task_id="task-abc123"
)
MessageBus.send(msg)

# Receive messages
inbox = MessageBus.get_inbox("kimi")
```

### 4. Transport Layer

The transport layer abstracts message/task I/O:

| Transport | Type | Use Case |
|-----------|------|----------|
| `LocalTransport` | local | Single-machine collaboration (default) |
| `GitTransport` | git | Cross-machine via orphan branch |
| `HttpTransport` | http | AgentWeave Hub (self-hosted or hosted) |

Transport selection is automatic based on `.agentweave/transport.json`.

**BaseTransport ABC (6 methods):**
```python
class BaseTransport(ABC):
    @abstractmethod
    def send_message(self, message_data: Dict[str, Any]) -> bool: ...
    @abstractmethod
    def get_pending_messages(self, agent: str) -> List[Dict[str, Any]]: ...
    @abstractmethod
    def archive_message(self, message_id: str) -> bool: ...
    @abstractmethod
    def send_task(self, task_data: Dict[str, Any]) -> bool: ...
    @abstractmethod
    def get_active_tasks(self, agent: Optional[str] = None) -> List[Dict[str, Any]]: ...
    @abstractmethod
    def get_transport_type(self) -> str: ...
```

### 5. File Locking

All task file operations that modify state must use locking:

```python
from agentweave.locking import lock

with lock("task-abc123"):
    task = Task.load("task-abc123")
    task.update(status="completed")
    task.save()
```

Locks have a 5-minute automatic timeout to prevent deadlocks.

### 6. Validation

All saves must pass through validator functions:

```python
from agentweave.validator import validate_task, sanitize_task_data

is_valid, errors = validate_task(task_data)
if is_valid:
    sanitized = sanitize_task_data(task_data)
    # ... save
```

### 7. Event Logging

Structured events are logged to `.agentweave/logs/events.jsonl`:

```python
from agentweave.eventlog import log_event, INFO, WARN, ERROR

log_event("task_created", task_id=task.id, title=task.title)
log_event("custom_event", severity=WARN, detail="something happened")
```

### 8. MCP Server Tools

When MCP is enabled, agents have these native tools:

| Tool | What it does |
|------|-------------|
| `send_message(from, to, subject, content)` | Send a message to another agent |
| `get_inbox(agent)` | Read unread messages |
| `mark_read(message_id)` | Archive a message after processing |
| `list_tasks(agent?)` | List active tasks |
| `get_task(task_id)` | Get task details |
| `update_task(task_id, status)` | Update task status |
| `create_task(title, ...)` | Create and assign a new task |
| `get_status()` | Session-wide summary + task counts |
| `ask_user(from_agent, question)` | Post a question to the human (Hub only) |
| `get_answer(question_id)` | Check if human answered (Hub only) |

## Code Style Guidelines

### Python Style

- **Line length**: 100 characters (configured in `pyproject.toml`)
- **Formatter**: black
- **Linter**: ruff
- **Type hints**: Required (enforced by mypy)

### Naming Conventions

- **Modules**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions/Variables**: `snake_case`
- **Constants**: `UPPER_CASE` (defined in `constants.py`)

### Critical Rules

1. **Agent name validation**: Use `AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")` from `constants.py`. Any name matching this regex is accepted.

2. **Never hardcode template strings**: Use `get_template("name")` from `templates/__init__.py`.

3. **Always use locking**: Task modifications must use `with lock("name"):`.

4. **Always validate**: Run `validate_task()` and `sanitize_task_data()` before saving.

5. **Never modify working tree in GitTransport**: Use only git plumbing commands (`hash-object`, `mktree`, `commit-tree`, `push`).

6. **is_locked() is read-only**: Never delete files in `is_locked()` — only `acquire_lock()` cleans stale locks.

7. **HttpTransport uses stdlib only**: `urllib.request` — no new CLI dependencies.

## Testing Strategy

### Test Structure

```
tests/
├── __init__.py
├── test_session.py      # Session CRUD operations
├── test_task.py         # Task lifecycle
├── test_messaging.py    # Message routing
├── test_validator.py    # Validation functions
├── test_locking.py      # Locking mechanism
├── test_transport_local.py  # Local transport
└── test_http_transport.py   # HTTP transport
```

### Hub Tests

```
hub/tests/
├── __init__.py
├── conftest.py
├── test_auth.py
├── test_messages.py
├── test_tasks.py
├── test_questions.py
├── test_sse.py
└── test_status.py
```

### Running Tests

```bash
# CLI tests only
pytest tests/ -v

# Hub tests only
pytest hub/tests/ -v

# All tests with coverage
make test-all
```

## Security Considerations

1. **File locking**: Prevents race conditions when multiple agents write simultaneously.

2. **Schema validation**: All JSON state files are validated before saving.

3. **Input sanitization**: String length limits and type coercion before any write.

4. **Path traversal protection**: Task IDs are validated with regex `^[a-zA-Z0-9_-]+$` before file operations.

5. **Git transport safety**:
   - Uses git plumbing only — never touches working tree or HEAD
   - UUID-suffixed filenames prevent conflicts between concurrent pushes
   - Retry logic with exponential backoff for push conflicts

6. **API security (Hub)**:
   - API key format: `aw_live_{random32}` — never commit keys
   - Bearer token authentication on all endpoints
   - Project-scoped access control

## Deployment Process

### PyPI Release (CLI)

```bash
# Build distribution
python -m build

# Upload to PyPI
python -m twine upload dist/*
```

### Version Management

Version is defined in:
- `pyproject.toml` (`[project]` section): **0.5.0**
- `src/agentweave/__init__.py` (`__version__`)

Keep these in sync when bumping versions.

### Hub Deployment

```bash
# End-user install (no source needed)
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/docker-compose.yml
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/.env.example
cp .env.example .env  # edit AW_BOOTSTRAP_API_KEY
docker compose up -d

# Build from source
cd hub && docker compose up --build -d
```

## Entry Points

Defined in `pyproject.toml` `[project.scripts]`:

| Command | Entry Point | Purpose |
|---------|-------------|---------|
| `agentweave` | `agentweave.cli:main` | Main CLI |
| `aw` | `agentweave.cli:main` | CLI alias |
| `agentweave-watch` | `agentweave.watchdog:main` | File watchdog daemon |
| `agentweave-mcp` | `agentweave.mcp.server:main` | MCP server (stdio) |

## Role Management

Agents can have multiple roles assigned. Roles define responsibilities and are used to:
- Generate appropriate AI_CONTEXT.md sections
- Copy role-specific guides to `.agentweave/roles/{role}.md`
- Sync to Hub when using HTTP transport

### CLI Commands

```bash
# List all agents and their roles
agentweave roles list

# Add a role to an agent
agentweave roles add <agent> <role_id>

# Remove a role from an agent
agentweave roles remove <agent> <role_id>

# Set multiple roles for an agent (replaces existing)
agentweave roles set <agent> <role1,role2,...>

# List available role types
agentweave roles available
```

### Available Roles

Roles are defined in `src/agentweave/templates/roles/`:

| Role ID | Label | Description |
|---------|-------|-------------|
| `backend_dev` | Backend Developer | API, database, business logic |
| `frontend_dev` | Frontend Developer | UI components, user experience |
| `tech_lead` | Technical Lead | Architecture, code review, standards |
| `qa_engineer` | QA Engineer | Testing, quality assurance |
| `devops_engineer` | DevOps Engineer | Infrastructure, CI/CD, deployment |
| `security_engineer` | Security Engineer | Security review, compliance |
| `docs_writer` | Documentation Writer | User docs, API docs, guides |
| `product_manager` | Product Manager | Requirements, prioritization |
| `project_manager` | Project Manager | Planning, coordination, tracking |
| `ui_designer` | UI Designer | Visual design, design systems |
| `ux_researcher` | UX Researcher | User research, usability testing |
| `data_engineer` | Data Engineer | Data pipelines, warehousing |
| `data_scientist` | Data Scientist | ML models, analytics, insights |
| `mobile_dev` | Mobile Developer | iOS/Android apps |

### Configuration

Roles are stored in `.agentweave/roles.json`:

```json
{
  "version": 2,
  "agent_roles": {
    "claude": ["tech_lead", "backend_dev"],
    "kimi": ["backend_dev"],
    "gemini": ["frontend_dev"]
  },
  "roles_defs": {
    "backend_dev": {"label": "Backend Developer", ...},
    ...
  }
}
```

**Backward compatibility**: Legacy `agent_assignments` (single role per agent) is automatically migrated to `agent_roles` (array).

### Programmatic API

```python
from agentweave.roles import (
    load_roles_config,
    add_role_to_agent,
    remove_role_from_agent,
    set_agent_roles,
    get_agent_roles,
    copy_role_md_file,
    sync_roles_to_hub,
)

# Load config
config = load_roles_config()

# Add role
success, message, config = add_role_to_agent("kimi", "backend_dev", config)

# Set multiple roles
success, message, config = set_agent_roles("kimi", ["backend_dev", "qa_engineer"], config)

# Sync to Hub (if HTTP transport active)
sync_roles_to_hub(config)
```

## Adding New Features

### Adding a CLI Command

1. Add `cmd_<name>()` function in `cli.py`
2. Add subparser in `create_parser()` function
3. Add routing branch in `main()` function

### Adding a Transport

1. Create class in `transport/<name>.py` extending `BaseTransport`
2. Implement all 6 abstract methods
3. Add `elif transport_type == "..."` branch in `transport/config.py`
4. Add CLI handling in `cmd_transport_setup()`

### Adding a Template

1. Create `.md` file in `templates/`
2. Reference via `get_template("filename_without_extension")`

### Adding an MCP Tool

1. Add `@mcp.tool()` decorated function in `mcp/server.py`
2. Import and use existing core modules (session, task, messaging)
3. Follow existing patterns for error handling and return types

## Files to Never Commit

The following are gitignored and should never be committed:

- `.agentweave/tasks/*/` — Task state files
- `.agentweave/messages/*/` — Message state files
- `.agentweave/agents/*.json` — Agent status
- `.agentweave/session.json` — Session config
- `.agentweave/transport.json` — Transport config (may contain secrets)
- `.agentweave/.git_seen/` — Git transport seen-set
- `.agentweave/logs/` — Event logs
- `.agentweave/watchdog.pid` — Watchdog PID
- `.agentweave/watchdog.log` — Watchdog logs
- `kimichanges.md`, `kimiwork.md` — Working files

**Safe to commit**:
- `.agentweave/README.md`
- `.agentweave/protocol.md`
- `.agentweave/roles.json`
- `.agentweave/roles/*.md`
- `.agentweave/ai_context.md`
- `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` (project root — agent-specific context files)

## Resources

- **GitHub**: https://github.com/gutohuida/AgentWeave
- **PyPI**: https://pypi.org/project/agentweave-ai/
- **Issues**: https://github.com/gutohuida/AgentWeave/issues
- **Roadmap**: `ROADMAP.md` in repository root
