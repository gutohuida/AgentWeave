# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.9.3] - 2026-03-26

### Fixed
- **Hub re-init API key mismatch**: on `agentweave init` when Hub was already running, a new API key was generated and written to `.env` but the running container still used the old key — causing `_sync_session_to_hub` to get 401 and all agents to fail syncing. Fix: read existing `AW_BOOTSTRAP_API_KEY` from `.env` and reuse it; only generate a new key when `.env` doesn't exist.
- **Uncaught `[Errno 2]` during init**: `shared/context.md` write in `_create_session_files()` was not wrapped in error handling — any OS-level write failure propagated as an unhandled exception showing `[ERR] Unexpected error: [Errno 2] No such file or directory`. Wrapped with `contextlib.suppress(OSError)`.
- **Improved error reporting**: `main()` catch-all now prints the full traceback alongside the error message to aid diagnosis.

---

## [0.9.2] - 2026-03-26

### Fixed
- **Hub agent sync on init**: agents created during `agentweave init` are now immediately synced to the Hub when HTTP transport is configured — previously they were never pushed to the Hub database, causing three visible issues: gemini (and any agent created at init) not appearing in the Hub UI, YOLO mode always showing as disabled, and stale principal roles from earlier syncs persisting in the Hub

---

## [0.9.1] - 2026-03-26

### Fixed (CLI)
- **File handle leak**: `log_fh` is now closed immediately after `Popen()` in `cmd_start` — prevents fd accumulation on repeated start/stop cycles
- **Unlink safety**: all `PID_FILE.unlink()` calls in `cmd_start` / `cmd_stop` now use `missing_ok=True` to avoid `FileNotFoundError` on race conditions
- **Redundant import**: removed `import os as _os` inside `cmd_start` (was already imported as `os`)
- **Version fallback**: `__init__.py` fallback updated to `0.9.1` (was stuck at `0.8.0`)
- Ruff lint cleanup (87 auto-fixed + 5 manual): removed blank-line whitespace, fixed import order, removed unused import, fixed E402 in `utils.py`
- Black formatting applied to `cli.py` and `watchdog.py`

### Fixed (Hub v0.4.0)
- **`await session.delete()` crash**: `AsyncSession.delete()` is synchronous; removed erroneous `await` in agent config deletion endpoint — endpoint would raise `TypeError` at runtime
- **MCP server hang**: added `timeout=30` to `urllib.request.urlopen()` in `_hub_request()` — previously could hang indefinitely if Hub was unreachable
- **Import inconsistency**: `settings.py` now uses relative import `from ...auth import get_project` (was absolute `from hub.auth`)
- **Dockerfile.dev**: removed unused `aiohttp` dependency (not in `pyproject.toml`, not imported anywhere)

### Added (Hub v0.4.0)
- **Agent config UI**: Hub dashboard now shows agent configurations synced from CLI (`/agents/configs` endpoint with `AgentConfigResponse` schema)
- **Watchdog enhancements**: improved trigger handling and HTTP transport reliability
- **M3 styling fixes**: dashboard UI refinements

---

## [0.9.0] - 2026-03-23

### Added
- **Gemini CLI support**: dedicated `gemini_context.md` template; correct MCP
  command format (`gemini mcp add agentweave <cmd>`) in `agentweave mcp-setup`
- **OpenCode support**: dedicated `opencode_context.md` template; `OPENCODE.md`
  as context file; added to `KNOWN_AGENTS`, default roles, and agent list in
  interactive wizard
- **Interactive wizard**: star (★) indicator distinguishes agents with dedicated
  context files (claude, kimi, gemini, opencode) from generic AGENTS.md agents
- **Deploy skills**: `aw-deploy` skill gains auto change-detection step (detects
  CLI vs Hub changes since last tag); `aw-check-ci` skill for monitoring GitHub
  Actions CI/CD, auto-fixing lint/type/test failures, and pushing fixes
- **Gitignore**: `hub/data/` and `.agentweave/logs/` added to `.gitignore`

### Fixed
- Mypy type errors in `interactive.py` and `hub_setup.py`
- Ruff lint errors in `interactive.py`
- Black formatting across `cli.py`, `interactive.py`, `hub_setup.py`

---

## [0.1.0] - 2024-03-07

### Added
- Initial release of AgentWeave
- Core session management
- Task creation and management
- Messaging system between agents
- CLI tool (`agentweave` command)
- Python API for programmatic use
- File-based protocol using `.agentweave/` directory
- Support for Claude and Kimi collaboration
- Role-based collaboration (Principal, Delegate, Reviewer)
- Task status tracking (pending → assigned → in_progress → completed → approved)
- Message inbox system
- Example scripts (basic_workflow, parallel_workflow)
- CLI examples (bash and batch)
- Markdown templates for tasks and reviews
- Comprehensive documentation

### Features
- **Session Management**: Initialize and manage collaboration sessions
- **Task Delegation**: Create and assign tasks to agents
- **Status Tracking**: Track task progress through workflow
- **Messaging**: Send messages between agents
- **Inbox System**: Check pending messages
- **Git Integration**: All state stored in Git-trackable files
- **Capability-Based Routing**: Automatic task assignment based on agent strengths

---

## [0.7.0] - 2026-03-22

### Added (CLI)
- **Auto-generated Claude Code skills on `agentweave init`**: running `init` now writes 8 ready-to-use `.claude/skills/` into the project, personalized with agent names, principal, and mode
  - `/aw-delegate` — delegate a task and auto-generate relay prompt when on local transport
  - `/aw-status` — full collaboration overview (tasks + inboxes + watchdog)
  - `/aw-done` — mark task complete and notify principal (safety-guarded)
  - `/aw-review` — request a code review from the reviewer agent
  - `/aw-relay` — generate relay prompt for manual handoff
  - `/aw-sync` — sync all agent context files from `ai_context.md`
  - `/aw-revise` — accept a revision and notify principal
  - `aw-collab-start` — auto-invoked session checklist (reads role, inbox, tasks)
- **Template improvements** based on multi-agent best practices research (Anthropic, Google ADK, OpenAI Swarm):
  - Security Guardrails section in `claude_context.md`, `kimi_context.md`, `ai_context.md` — hardcoded secrets, shell injection, SSL, path traversal
  - Performance Guardrails section — N+1 queries, blocking I/O, unbounded loops
  - Phase Discipline section — Explore → Plan → Implement → Verify workflow
  - Escalation Path table — 6 clear situations with explicit actions
  - `task_delegation.md` gains 5 new fields: Phase, Constraints, Output Format, Verification, Escalation Path
  - `collab_protocol.md` gains structured Handoff Message Format and Phase-Based Delegation table
  - `review_request.md` gains Review Scope selector and Verification checklist for reviewers
  - `kimi_context.md` synced with `claude_context.md` — Sub-Agent Setup section added
- **`aw-deploy` project skill** at `.claude/skills/aw-deploy/` — full release workflow for maintainers

### Added (Hub v0.3.0)
- **Agent Chat API** (`GET /api/v1/agent/{agent}/chat/{session_id}`): retrieves structured chat history for a given agent session, merging messages and agent output into a unified timeline
- **AgentPromptPanel UI component**: displays per-agent chat history in the dashboard with auto-scroll and live updates
- **AgentPromptMessage UI component**: renders individual chat messages with role-based styling (user vs agent)
- **agentChat API client** (`hub/ui/src/api/agentChat.ts`): React hooks `useAgentChatHistory` and `useAgentRecentChat` for polling agent conversation history

---

## [0.6.1] - 2026-03-21

### Added (Hub UI v0.2.1)
- **Expandable TaskCard**: tasks now expand inline to show requirements, acceptance criteria, deliverables, and notes
- **Expandable MessageCard**: long messages truncate with click-to-expand; message type and task ID chips in footer; subject shown as a labelled field
- Task interface extended with `assigner`, `requirements`, `acceptance_criteria`, `deliverables`, `notes` fields
- Assigner badge shown on task cards when assigner differs from assignee

### Fixed (Hub)
- `questions.py`: reply message sender changed from `"human"` to `"user"` for consistency with message schema

---

## [0.6.0] - 2026-03-19

### Added (CLI)
- Agent-specific context templates: `claude_context.md`, `kimi_context.md`, `collab_protocol.md` — generated via `agentweave update-template --agent <name>`
- `collab_protocol.md` template for cross-agent protocol documentation
- Session start checklist and role adherence rules embedded in agent context templates

### Removed (CLI)
- `agents_guide.md` template — replaced by per-agent context templates

### Added (Hub v0.2.0)
- **Agent Trigger endpoint** (`POST /api/v1/agent/trigger`): triggers an agent from the Hub UI; creates a message the host-side watchdog picks up and executes on the host machine — CLIs do not need to run inside Docker
- **Agent session listing** (`GET /api/v1/agent/sessions/{agent}`): returns available CLI sessions for an agent
- **Agent Configurator UI**: component to add/remove configured agents (reads from `session.json` or manual list)
- **Agent Message Sender UI**: compose and send messages to agents directly from the dashboard, with session resume support
- **Agent configure endpoints**: `POST/DELETE/GET /api/v1/agents/configure` for managing the configured agent list per project
- `Icon` common component and `useCopy` hook for the dashboard
- `hub/Dockerfile.dev` for hot-reload development workflow
- Static files support in Hub (`hub/hub/static/`)

### Changed (Hub)
- Major UI refresh across all dashboard components (AgentsPage, ActivityLog, EventRow, AgentCard, AgentOutputPanel, Sidebar, StatusBar, LogLine, LogsView, MessageCard, MessagesFeed, QuestionsPanel, TaskCard, TasksBoard, Badge, EmptyState, SetupModal)
- Tailwind config and global CSS overhaul for consistent dark theme styling

---

## [0.5.1] - 2026-03-15

### Added
- Hub UI glassmorphism redesign: animated background orbs, frosted glass panels, full dark theme
- Color theme picker in Hub settings (Ocean Deep, Cosmic Purple, Solar Flare, Forest Night, Neon Rose)
- Agent output streaming to Hub UI with thinking block rendering
- Kimi output parser and stderr capture for agent diagnostics
- Watchdog resilience: crash recovery on transient Hub connection errors

### Fixed
- HTTP transport: two bug fixes in MCP server
- CI: all ruff, black, and mypy errors resolved; lint checks scoped to Python 3.11 to avoid black version skew
- pyproject.toml: corrected PEP 621 `license` field format

---

## [Unreleased]

### Planned
- Web dashboard for visualizing collaboration
- Desktop notifications
- Slack/Discord integration
- Additional agent profiles
- Plugin system
- VS Code extension

---

## Release Notes Template

```
## [X.Y.Z] - YYYY-MM-DD

### Added
- New features

### Changed
- Changes in existing functionality

### Deprecated
- Soon-to-be removed features

### Removed
- Removed features

### Fixed
- Bug fixes

### Security
- Security improvements
```
