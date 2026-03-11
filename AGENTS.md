# InterAgent Framework - Agent Guide

> This file provides essential information for AI coding agents working on the InterAgent Framework codebase.

## Project Overview

**InterAgent** is a multi-agent AI collaboration framework that enables multiple AI agents (Claude, Kimi, Gemini, Codex, etc.) to work together on the same project. Agents communicate through:

1. **A shared `.interagent/` directory** (filesystem-based protocol)
2. **A local MCP server** (for native tool integration)

The framework supports two modes:
- **Manual relay mode**: Zero dependencies, you paste relay prompts between agents
- **Zero-relay MCP mode**: Agents communicate autonomously via MCP tools

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.8+ |
| Package Manager | pip |
| Build System | setuptools (PEP 517) |
| Linting | ruff, black |
| Type Checking | mypy |
| Testing | pytest (not yet implemented) |
| MCP Server | fastmcp (optional dependency) |

## Project Structure

```
InterAgentFramework/
├── src/interagent/              # Main source code
│   ├── __init__.py              # Package exports
│   ├── cli.py                   # CLI commands (argparse) - main entry point
│   ├── session.py               # Session lifecycle management
│   ├── task.py                  # Task CRUD operations
│   ├── messaging.py             # MessageBus for agent communication
│   ├── locking.py               # File-based mutex for concurrency
│   ├── validator.py             # JSON schema validation
│   ├── watchdog.py              # File monitoring daemon
│   ├── constants.py             # All constants and valid values
│   ├── utils.py                 # Utility functions
│   ├── templates/               # Markdown prompt templates
│   │   ├── agents_guide.md      # Collaboration guide template
│   │   ├── ai_context.md        # AI context template
│   │   ├── roles_template.md    # Roles assignment template
│   │   └── ...
│   ├── transport/               # Pluggable transport layer
│   │   ├── base.py              # BaseTransport ABC
│   │   ├── local.py             # Local filesystem transport
│   │   ├── git.py               # Git orphan branch transport
│   │   ├── http.py              # HTTP/MCP transport (stub)
│   │   └── config.py            # Transport factory
│   └── mcp/                     # MCP server implementation
│       └── server.py            # FastMCP-based MCP server
├── examples/                    # Usage examples
│   ├── basic_workflow.py
│   └── parallel_workflow.py
├── pyproject.toml               # Package configuration
├── README.md                    # User documentation
├── CLAUDE.md                    # Claude Code guidance
├── ROADMAP.md                   # Development roadmap
└── AGENTS.md                    # This file
```

## Build and Development Commands

### Installation

```bash
# Development install (editable)
pip install -e ".[dev]"

# With MCP support
pip install -e ".[mcp]"

# With all extras
pip install -e ".[all]"
```

### Code Quality

```bash
# Linting (line length: 100)
ruff check src/

# Formatting
black src/

# Type checking
mypy src/
```

### Testing

```bash
# Run tests (pytest configured in pyproject.toml)
pytest

# With coverage
pytest --cov
```

**Note**: The `tests/` directory does not yet exist and needs to be created.

### CLI Verification

```bash
# Verify installation
interagent --help
iaf --help                    # alias
interagent-watch --help       # watchdog
interagent-mcp                # MCP server (stdio)
```

## Key Architectural Concepts

### 1. Session Management

Sessions are stored in `.interagent/session.json`:

```python
from interagent import Session

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

### 2. Task Lifecycle

Valid statuses (defined in `constants.py`):

```
pending → assigned → in_progress → completed → under_review → approved
                                             ↘ revision_needed (loops back)
                                             ↘ rejected
```

Task operations:
```python
from interagent import Task

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
from interagent import Message, MessageBus

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
| `LocalTransport` | local | Single-machine collaboration |
| `GitTransport` | git | Cross-machine via orphan branch |
| `HttpTransport` | http | InterAgent Hub (planned) |

Transport selection is automatic based on `.interagent/transport.json`.

### 5. File Locking

All task file operations that modify state must use locking:

```python
from interagent.locking import lock

with lock("task-abc123"):
    task = Task.load("task-abc123")
    task.update(status="completed")
    task.save()
```

Locks have a 5-minute automatic timeout to prevent deadlocks.

### 6. Validation

All saves must pass through validator functions:

```python
from interagent.validator import validate_task, sanitize_task_data

is_valid, errors = validate_task(task_data)
if is_valid:
    sanitized = sanitize_task_data(task_data)
    # ... save
```

### 7. MCP Server Tools

When MCP is enabled, agents have these native tools:

- `send_message(from_agent, to_agent, subject, content)`
- `get_inbox(agent)` - Read unread messages
- `mark_read(message_id)` - Archive a message
- `list_tasks(agent?)` - List active tasks
- `get_task(task_id)` - Get task details
- `update_task(task_id, status)` - Update task status
- `create_task(title, description, assignee, ...)` - Create task
- `get_status()` - Session summary

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

6. **is_locked() is read-only**: Never delete files in `is_locked()` - only `acquire_lock()` cleans stale locks.

## Testing Strategy

**Current state**: No tests exist yet. The test infrastructure is configured in `pyproject.toml`.

**Planned testing approach**:

1. **Unit tests** for:
   - `Session` CRUD operations
   - `Task` lifecycle
   - `Message` creation and routing
   - `validator` functions
   - `locking` mechanism

2. **Integration tests** for:
   - Transport layer (with mocked git)
   - CLI commands
   - MCP server tools

3. **Test structure** (to be created):
   ```
   tests/
   ├── __init__.py
   ├── test_session.py
   ├── test_task.py
   ├── test_messaging.py
   ├── test_validator.py
   ├── test_locking.py
   ├── test_transport/
   │   ├── test_local.py
   │   └── test_git.py
   └── test_cli.py
   ```

## Security Considerations

1. **File locking**: Prevents race conditions when multiple agents write simultaneously.

2. **Schema validation**: All JSON state files are validated before saving.

3. **Input sanitization**: String length limits and type coercion before any write.

4. **Path traversal protection**: Task IDs are validated with regex `^[a-zA-Z0-9_-]+$` before file operations.

5. **Git transport safety**:
   - Uses git plumbing only - never touches working tree or HEAD
   - UUID-suffixed filenames prevent conflicts
   - Retry logic with exponential backoff for push conflicts

## Deployment Process

### PyPI Release

```bash
# Build distribution
python -m build

# Upload to PyPI
python -m twine upload dist/*
```

### Version Management

Version is defined in:
- `pyproject.toml` (`[project]` section)
- `src/interagent/__init__.py` (`__version__`)

Keep these in sync when bumping versions.

## Entry Points

Defined in `pyproject.toml` `[project.scripts]`:

| Command | Entry Point | Purpose |
|---------|-------------|---------|
| `interagent` | `interagent.cli:main` | Main CLI |
| `iaf` | `interagent.cli:main` | CLI alias |
| `interagent-watch` | `interagent.watchdog:main` | File watchdog |
| `interagent-mcp` | `interagent.mcp.server:main` | MCP server |

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

## Files to Never Commit

The following are gitignored and should never be committed:

- `.interagent/tasks/*/` - Task state files
- `.interagent/messages/*/` - Message state files
- `.interagent/agents/*.json` - Agent status
- `.interagent/session.json` - Session config
- `.interagent/transport.json` - Transport config (may contain secrets)
- `.interagent/.git_seen/` - Git transport seen-set
- `.interagent/watchdog.pid` - Watchdog PID
- `.interagent/watchdog.log` - Watchdog logs
- `kimichanges.md`, `kimiwork.md` - Working files

**Safe to commit**:
- `.interagent/README.md`
- `.interagent/AGENTS.md`
- `.interagent/ROLES.md`

## Resources

- **GitHub**: https://github.com/gutohuida/InterAgentFramework
- **PyPI**: https://pypi.org/project/interagent-framework/
- **Issues**: https://github.com/gutohuida/InterAgentFramework/issues
- **Roadmap**: `ROADMAP.md` in repository root
