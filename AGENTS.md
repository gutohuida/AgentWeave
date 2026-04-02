# AgentWeave Framework - Agent Guide

> This file provides essential information for AI coding agents working on the **AgentWeave Framework** codebase itself (v0.15.0).

## Project Overview

**AgentWeave** is a multi-agent AI collaboration framework that enables multiple AI agents (Claude, Kimi, Gemini, Codex, Minimax, GLM, and more) to work together on the same project.

This repository contains the framework source code — NOT a project using AgentWeave. You are working on:
- **CLI package** (`src/agentweave/`) — Python 3.8+, zero runtime dependencies
- **Hub server** (`hub/`) — FastAPI backend + React dashboard for web-based collaboration
- **Documentation site** (`docs/`) — MkDocs with Material theme

### Three Operation Modes

| Mode | How it works | Best for |
|------|--------------|----------|
| **Hub** (recommended) | Self-hosted FastAPI server with web dashboard | Teams, multi-machine, real-time monitoring |
| **Zero-relay MCP** | MCP tools + watchdog daemon | Autonomous loops, same machine |
| **Manual relay** | Paste relay prompts between agents | Quick one-off delegation |

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.8+ (CLI), TypeScript/React (Hub UI) |
| Package Manager | pip (CLI), npm (Hub UI) |
| Build System | setuptools (PEP 517) |
| CLI Linting/Formatting | ruff, black |
| CLI Type Checking | mypy |
| Testing | pytest |
| MCP Server | fastmcp |
| Hub Backend | FastAPI + SQLAlchemy + SQLite/PostgreSQL |
| Hub Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Docs | MkDocs + Material |

## Repository Layout

```
AgentWeave/
├── src/agentweave/              # CLI package (v0.15.0)
│   ├── __init__.py              # Package exports and version
│   ├── cli.py                   # All CLI commands (argparse)
│   ├── session.py               # Session lifecycle management
│   ├── task.py                  # Task CRUD operations
│   ├── messaging.py             # MessageBus for agent communication
│   ├── locking.py               # File-based mutex for concurrency
│   ├── validator.py             # JSON schema validation
│   ├── watchdog.py              # File monitoring daemon with auto-ping
│   ├── eventlog.py              # Event logging (read-path utilities)
│   ├── runner.py                # Agent runner helpers (claude_proxy support)
│   ├── roles.py                 # Multi-role agent management
│   ├── constants.py             # All constants and valid values
│   ├── utils.py                 # Utility functions
│   ├── logging_config.py        # Python logging stdlib configuration
│   ├── templates/               # Markdown prompt templates
│   │   ├── __init__.py          # Template loader
│   │   ├── ai_context.md        # AI context template
│   │   ├── roles/               # Role-specific guides
│   │   │   ├── backend_dev.md
│   │   │   ├── frontend_dev.md
│   │   │   └── ...
│   │   └── ...
│   ├── transport/               # Pluggable transport layer
│   │   ├── base.py              # BaseTransport ABC
│   │   ├── local.py             # Local filesystem transport
│   │   ├── git.py               # Git orphan branch transport
│   │   ├── http.py              # HTTP/REST transport for Hub
│   │   └── config.py            # Transport factory
│   └── mcp/                     # MCP server implementation
│       └── server.py            # FastMCP-based MCP server
│
├── hub/                         # AgentWeave Hub (v0.9.0)
│   ├── hub/                     # Python package
│   │   ├── main.py              # FastAPI app factory
│   │   ├── mcp_server.py        # Hub-side MCP server (11 tools)
│   │   ├── db/                  # SQLAlchemy models
│   │   ├── api/v1/              # REST API endpoints
│   │   │   ├── agents.py        # Agent management
│   │   │   ├── messages.py      # Message CRUD
│   │   │   ├── tasks.py         # Task CRUD
│   │   │   ├── questions.py     # Human questions
│   │   │   ├── events.py        # SSE endpoint
│   │   │   ├── logs.py          # Agent output logs
│   │   │   ├── agent_chat.py    # Per-agent chat history
│   │   │   ├── agent_trigger.py # Trigger agent endpoint
│   │   │   └── ...
│   │   └── schemas/             # Pydantic schemas
│   ├── ui/                      # React dashboard
│   │   ├── src/
│   │   │   ├── App.tsx
│   │   │   ├── api/             # API client hooks
│   │   │   │   ├── agents.ts    # Agent queries + SSE
│   │   │   │   ├── messages.ts
│   │   │   │   ├── tasks.ts
│   │   │   │   ├── agentChat.ts # Chat history
│   │   │   │   └── ...
│   │   │   ├── components/
│   │   │   │   ├── agents/      # Agent UI components
│   │   │   │   │   ├── AgentsPage.tsx
│   │   │   │   │   ├── AgentCard.tsx
│   │   │   │   │   ├── AgentPromptPanel.tsx    # Chat interface
│   │   │   │   │   ├── AgentOutputPanel.tsx    # Output logs
│   │   │   │   │   ├── AgentActivityTab.tsx
│   │   │   │   │   └── ...
│   │   │   │   ├── tasks/       # Task board components
│   │   │   │   ├── messages/    # Message feed components
│   │   │   │   ├── questions/   # Human Q&A panel
│   │   │   │   ├── logs/        # Log viewer
│   │   │   │   └── layout/      # Sidebar, status bar
│   │   │   ├── store/           # Zustand stores
│   │   │   └── hooks/           # Custom React hooks
│   │   └── package.json
│   ├── docker-compose.yml
│   └── Dockerfile
│
├── tests/                       # CLI unit tests (pytest)
├── docs/                        # MkDocs documentation
│   ├── index.md
│   ├── getting-started/
│   ├── guides/
│   ├── reference/
│   └── architecture/
│
├── pyproject.toml               # CLI package config
├── README.md                    # User documentation
├── CHANGELOG.md                 # Release notes
├── ROADMAP.md                   # Future plans
├── AGENTS.md                    # This file — for framework contributors
└── CLAUDE.md                    # Claude-specific guidance
```

## Build and Development Commands

### CLI Development

```bash
# Development install (editable)
pip install -e ".[dev]"

# With MCP support
pip install -e ".[mcp]"

# With all extras
pip install -e ".[all]"

# Code quality
ruff check src/          # Linting (line length: 100)
black src/               # Formatting
mypy src/                # Type checking

# Testing
pytest tests/ -v
pytest tests/ -v --cov=agentweave --cov-report=term-missing
```

### Hub Development

```bash
# Start Hub for development
cd hub
docker compose up -d

# UI development (hot-reload)
cd hub/ui
npm install
npm run dev              # http://localhost:5173

# Build UI for production
npm run build            # Outputs to dist/
```

### Documentation

```bash
# Serve docs locally
mkdocs serve

# Build docs
mkdocs build

# Deploy (CI/CD handles this)
mkdocs gh-deploy
```

## Key Architectural Concepts

### 1. Multi-Role Agent System (v0.15.0)

Agents can have multiple roles assigned simultaneously:

```python
from agentweave.roles import add_role_to_agent, set_agent_roles

# Add single role
add_role_to_agent("kimi", "backend_dev", config)

# Set multiple roles
set_agent_roles("claude", ["tech_lead", "backend_dev"], config)
```

Available roles: `backend_dev`, `frontend_dev`, `tech_lead`, `qa_engineer`, `devops_engineer`, `security_engineer`, `docs_writer`, `product_manager`, `project_manager`, `ui_designer`, `ux_researcher`, `data_engineer`, `data_scientist`, `mobile_dev`

Role guides are auto-copied to `.agentweave/roles/{role}.md` when assigned.

### 2. Claude-Proxy Agents (v0.12.0+)

Run Minimax, GLM, or any OpenAI-compatible model through Claude Code CLI:

```bash
# Configure proxy agent
agentweave agent configure minimax --runner claude_proxy

# Switch to proxy in shell
eval $(agentweave switch minimax)

# Run with automatic delegation
agentweave run --agent minimax "task description"
```

Built-in providers in `CLAUDE_PROXY_PROVIDERS`:
- **minimax**: Default model `MiniMax-Text-01`
- **glm**: Default model `glm-5`

### 3. Transport Layer

| Transport | Type | Use Case |
|-----------|------|----------|
| `LocalTransport` | local | Single-machine collaboration |
| `GitTransport` | git | Cross-machine via orphan branch |
| `HttpTransport` | http | AgentWeave Hub |

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

### 4. Task Lifecycle

```
pending → assigned → in_progress → completed → under_review → approved
                                             ↘ revision_needed (loops back)
                                             ↘ rejected
```

### 5. Hub MCP Server Tools (11 tools)

| Tool | Purpose |
|------|---------|
| `send_message(from, to, subject, content)` | Send inter-agent message |
| `get_inbox(agent)` | Read unread messages |
| `mark_read(message_id)` | Archive message |
| `list_tasks(agent?)` | List active tasks |
| `get_task(task_id)` | Get task details |
| `update_task(task_id, status)` | Update task status |
| `create_task(title, ...)` | Create new task |
| `get_status()` | Session summary + counts |
| `ask_user(from_agent, question)` | Ask human (Hub only) |
| `get_answer(question_id)` | Check human answer |
| `get_agent_config(agent)` | Get agent runner config |

### 6. Logging Architecture (v0.11.0+)

Uses Python `logging` stdlib with two handlers:
- `JSONRotatingFileHandler`: Writes to `.agentweave/logs/events.jsonl` (10MB rotation, 5 backups)
- `HubHandler`: Forwards INFO+/WARNING+/ERROR+ to Hub when HTTP transport active

Environment variables:
- `AW_LOG_LEVEL`: Default `WARNING`
- `AW_LOG_FILE`: Optional custom log path

### 7. Hub UI Components

Key React components in `hub/ui/src/components/`:

| Component | Purpose |
|-----------|---------|
| `AgentsPage.tsx` | Main agent list + detail view |
| `AgentPromptPanel.tsx` | Chat interface with session selector |
| `AgentOutputPanel.tsx` | Real-time output log viewer |
| `AgentCard.tsx` | Agent summary card with roles badges |
| `TasksBoard.tsx` | Kanban-style task board |
| `MessagesFeed.tsx` | Inbox + message history |
| `QuestionsPanel.tsx` | Human Q&A interface |
| `LogsView.tsx` | Structured log viewer |

## Code Style Guidelines

### Python (CLI)

- **Line length**: 100 characters
- **Formatter**: black
- **Linter**: ruff
- **Type hints**: Required (enforced by mypy)

### TypeScript/React (Hub UI)

- **Formatter**: Prettier (via ESLint)
- **Linter**: ESLint
- **Style**: Functional components with hooks
- **State**: Zustand for global state, React Query for server state

### Naming Conventions

- **Modules**: `snake_case.py` / `camelCase.ts`
- **Classes**: `PascalCase`
- **Functions/Variables**: `snake_case` (Python) / `camelCase` (TS)
- **Constants**: `UPPER_CASE`

## Critical Rules

1. **Agent name validation**: Use `AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")` from `constants.py`

2. **Never hardcode template strings**: Use `get_template("name")` from `templates/__init__.py`

3. **Always use locking**: Task modifications must use `with lock("name"):`

4. **Always validate**: Run `validate_task()` and `sanitize_task_data()` before saving

5. **Never modify working tree in GitTransport**: Use only git plumbing commands

6. **is_locked() is read-only**: Never delete files in `is_locked()`

7. **HttpTransport uses stdlib only**: `urllib.request` — no new CLI dependencies

8. **UI uses React Query**: All API calls go through hooks in `hub/ui/src/api/`

9. **SSE for real-time updates**: Hub uses Server-Sent Events for live data

## Testing Strategy

### CLI Tests

```
tests/
├── test_session.py
├── test_task.py
├── test_messaging.py
├── test_validator.py
├── test_locking.py
├── test_transport_local.py
└── test_http_transport.py
```

### Hub Tests

```
hub/tests/
├── test_auth.py
├── test_messages.py
├── test_tasks.py
├── test_questions.py
├── test_sse.py
└── test_status.py
```

### UI Tests

Hub UI uses manual testing via browser. Key flows to verify:
1. Agent list loads and shows connected agents
2. Clicking agent opens chat with session selector
3. "New chat" button creates new conversation
4. Task board shows tasks and allows status updates
5. Messages feed displays inbox + history
6. Questions panel allows answering agent questions

## Recent Session Work (Agent Chat UI Fixes)

### April 1, 2026 — Session Routing & Chat History Fixes

Fixed critical end-to-end bugs where new-chat messages were routed to the wrong session and chat history either leaked across sessions or disappeared entirely.

#### Files Changed
- `src/agentweave/watchdog.py`
- `hub/hub/api/v1/agent_trigger.py`
- `hub/hub/api/v1/agent_chat.py`
- `hub/hub/db/models.py`
- `hub/hub/migrations/versions/0003_add_message_session_id.py`
- `hub/ui/src/components/agents/AgentPromptPanel.tsx`

#### Bug: New Chat Messages Routed to Previous Session
**Issue**: Clicking "New chat" and sending a message resumed the previous CLI session instead of creating a new one.
**Root Cause**: In `watchdog.py`, `_make_direct_trigger_callback()` fell back to `_load_agent_session()` when no `[Session: ...]` tag was found. This loaded the old `.agentweave/agents/{agent}-session.json` and passed `--resume <old_id>` to the CLI.
**Solution**: Removed the fallback. For Hub UI direct triggers, the absence of a session tag now explicitly means "start a new session."

#### Bug: Chat History Disappeared or Leaked Across Sessions
**Issue**: After earlier fixes, conversations either showed in every session (cross-leak) or vanished completely.
**Root Cause**: The chat history endpoint (`agent_chat.py`) had no reliable way to know which untagged `Message` row belonged to which session. Heuristics based on timestamps were too brittle — user messages are created *before* any agent output exists, so they fell outside calculated time windows and were excluded.
**Solution**:
1. Added `session_id` column to the `messages` table via Alembic migration `0003_add_message_session_id.py`.
2. Updated `agent_trigger.py` to store `session_id` on the `Message` row for resume-mode triggers.
3. Rewrote `agent_chat.py` to use a three-tier lookup:
   - Exact match on `Message.session_id` (post-migration resume messages)
   - Content fallback `[Session: {id}]` (pre-migration resume messages)
   - Time-window heuristic **only** for `session_id=NULL` new-session messages, with a 5-minute buffer before the first agent output

#### Bug: UI Blink and Lost Optimistic Messages
**Issue**: In new chat mode, the screen blinked and the user's optimistic message disappeared.
**Root Cause**: When the UI auto-switched from `new` to `resume` mode after detecting a session ID, the resume-mode effect replaced `localMessages` with `chatHistory` even when the history was still empty, wiping the optimistic temp message.
**Solution**:
- Added `chatHistory.messages.length > 0` guard before merging history into local state.
- Added `newSessionOutputIndexRef` so session detection only looks at output lines that arrived *after* clicking "New chat" — prevents immediately snapping back to a cached previous session.
- Merged history with existing local messages instead of replacing them, preserving temp messages and early agent outputs.

### March 31, 2026 — Session Management Bug Fixes

Fixed critical bugs in the Hub UI Agent Chat (`AgentPromptPanel.tsx`):

#### Bug 1: New Session Not Created
**Issue**: Clicking "New chat" kept resuming the last session instead of creating a new one.
**Root Cause**: Auto-selection effect was overriding user's choice.
**Solution**: Added `userChoseNewRef` to track when user explicitly wants a new session, preventing auto-selection from interfering.

#### Bug 2: Input Blocked in New Session  
**Issue**: After clicking "New chat", the input field was disabled.
**Root Cause**: `isInputDisabled` checked `selectedSessionId === NEW_SESSION_ID` which blocked input.
**Solution**: Removed the check — input should be enabled when user wants to start a new conversation.

#### Bug 3: Messages Routed to Wrong Session
**Issue**: Messages sent in a new session would disappear and appear in the previous session instead.
**Root Cause**: **Stale closure** in `handleSend`. The function captured `sessionMode` and `selectedSessionId` from the render where it was created. If user sent a message before React finished re-rendering after "New chat", stale values were used.
**Solution**: Added refs (`sessionModeRef`, `selectedSessionIdRef`) synced with state values. `handleSend` now reads from refs to always get current values, avoiding stale closures.

```typescript
// Pattern used to avoid stale closures
const sessionModeRef = useRef(sessionMode)
useEffect(() => { sessionModeRef.current = sessionMode }, [sessionMode])

// In handleSend, read from ref instead of closure
const currentMode = sessionModeRef.current
```

## Security Considerations

1. **File locking**: Prevents race conditions
2. **Schema validation**: All JSON state files validated before saving
3. **Path traversal protection**: Task IDs validated with regex before file operations
4. **API key format**: `aw_live_{random32}` — never commit keys
5. **Bearer token auth**: All Hub endpoints require authentication
6. **CORS**: Configurable via `AW_CORS_ORIGINS`

## Files to Never Commit

Gitignored and must never be committed:

- `.agentweave/tasks/*/`
- `.agentweave/messages/*/`
- `.agentweave/agents/*.json`
- `.agentweave/session.json`
- `.agentweave/transport.json` (may contain secrets)
- `.agentweave/.git_seen/`
- `.agentweave/logs/`
- `kimichanges.md`, `kimiwork.md`

Safe to commit:
- `.agentweave/README.md`
- `.agentweave/protocol.md`
- `.agentweave/roles.json`
- `.agentweave/roles/*.md`
- `.agentweave/ai_context.md`
- `CLAUDE.md`, `AGENTS.md`

## Resources

- **GitHub**: https://github.com/gutohuida/AgentWeave
- **PyPI**: https://pypi.org/project/agentweave-ai/
- **Documentation**: https://gutohuida.github.io/AgentWeave/
- **Issues**: https://github.com/gutohuida/AgentWeave/issues
- **Roadmap**: `ROADMAP.md`
