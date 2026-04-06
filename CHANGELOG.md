# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---
## [0.19.0] - 2026-04-05

### Added (CLI)
- **AW-Spec workflow skill templates** — 4 new skills for structured change management:
  - `/aw-spec-explore` — explore an idea and generate structured findings
  - `/aw-spec-propose` — create a structured proposal with design and tasks
  - `/aw-spec-apply` — implement a proposal with optional agent delegation
  - `/aw-spec-archive` — archive completed proposals
- **Documentation updates** — comprehensive docs for multi-role agents, new MCP tools, and dashboard features

### Added (Hub v0.13.0)
- **Agent UI improvements** — enhanced Agent Output Panel with session management
- **Agent Card enhancements** — runner type badges and improved role display

---
## [0.18.0] - 2026-04-05

### Added (CLI)
- **OpenSpec workflow skill templates** — 4 new skills for structured change management:
  - `aw-spec-explore` — explore an idea and generate structured findings
  - `aw-spec-propose` — create a structured proposal with design and tasks
  - `aw-spec-apply` — implement a proposal with optional agent delegation
  - `aw-spec-archive` — archive completed proposals

### Added (Hub v0.12.0)
- Code quality improvements — black formatting fixes across Hub and CLI

---


## [0.17.0] - 2026-04-02

### Added (CLI)
- **OpenSpec workflow** — new CLI commands and skills for structured change management:
  - `opsx explore`, `opsx propose`, `opsx apply`, `opsx archive`
- **New `aw-checkpoint` skill template** — save context checkpoints before handoffs
- **Enhanced context management** — updated `ai_context.md`, `claude_context.md`, `kimi_context.md`, and `collab_protocol.md`
- **Watchdog and session improvements** — better session lifecycle handling in CLI

### Added (Hub v0.11.0)
- **Mission Control UI** — new `MissionControlPage` for centralized agent oversight
- **Agent context API** — new `context.ts` endpoint and related backend support
- **MCP server enhancements** — additional tools for agent introspection
- **UI layout updates** — `Sidebar` and `StatusBar` improvements for better navigation
- **Agent trigger and agents API updates** — improved agent configuration and triggering

---

## [0.16.0] - 2026-04-02

### Added (CLI)
- **AgentWeave skills system** — 8 new collaboration skills in `.claude/skills/`:
  - `aw-collab-start` — orient yourself at the start of an AgentWeave session
  - `aw-delegate` — delegate a task to another agent
  - `aw-done` — mark a task as completed
  - `aw-relay` — generate a relay prompt for manual handoff
  - `aw-review` — request a code review
  - `aw-revise` — accept a revision request
  - `aw-status` — show full collaboration overview
  - `aw-sync` — regenerate agent context files
- **Session-based chat history** in Hub UI — messages now tracked per-session
- **Watchdog session routing fix** — new chat no longer falls back to previous session

### Added (Hub v0.10.0)
- **Database migration 0003** — adds `session_id` column to messages table
- **Three-tier chat history lookup** — exact match, content fallback, time-window heuristic
- **New UI components** — `AgentActivityTab`, `AgentInfoTab` for detailed agent views
- **UI stability fixes** — eliminated blink and lost optimistic messages in chat panel
- **Updated API endpoints** — `agent_chat.py` and `agent_trigger.py` session handling

---

## [0.15.0] - 2026-03-31

### Added (CLI)
- **Multi-role support for agents** — agents can now have multiple roles assigned simultaneously
- **New `agentweave roles` CLI commands**:
  - `agentweave roles list` — show all agents and their assigned roles
  - `agentweave roles add <agent> <role>` — add a role to an agent
  - `agentweave roles remove <agent> <role>` — remove a role from an agent
  - `agentweave roles set <agent> <role1,role2,...>` — set multiple roles for an agent (replaces existing)
  - `agentweave roles available` — list all available role types with descriptions
- **Role guide markdown files** — automatically copied to `.agentweave/roles/{role}.md` when adding roles
- **Backward compatibility** — legacy `agent_assignments` (single role) auto-converted to `agent_roles` (array)

### Added (Hub v0.9.0)
- **Hub sync for role changes** — roles automatically sync to Hub when HTTP transport is active
- **Multi-role display in dashboard** — agent cards show all assigned roles as badges
- **Hub API updated** — `dev_roles` and `dev_role_labels` arrays in AgentSummary schema

---

## [0.14.0] - 2026-03-31

### Added (CLI)
- **Documentation site** with MkDocs and Material theme
- **24 documentation pages** covering getting started, guides, reference, architecture, and contributing
- **GitHub Actions workflow** for automatic docs deployment to GitHub Pages
- **Role-based agent system** with `roles.json` configuration and per-role behavioral guides in `roles/*.md` 
- **New guides**: Session modes, Context files, Dashboard usage, FAQ
- **Expanded CLI reference** with all commands including logs, MCP, and context management

### Added (Hub v0.8.0)
- **Agent roles configuration** API endpoints for pushing and retrieving role assignments
- **Documentation site** hosted alongside the project

---

## [0.13.0] - 2026-03-31

### Fixed (CLI)
- **Watchdog output duplication**: `_parse_claude_stream_line` was emitting the `result` field from the final `result`-type JSONL message, which is a full copy of the already-streamed assistant response. The field is now ignored; only the cost line is emitted from `result` messages.
- **GLM provider config** (`CLAUDE_PROXY_PROVIDERS`): switched GLM base URL from `/paas/v4` (OpenAI-compatible) to `/anthropic` (Anthropic-compatible) and upgraded default model from `glm-4` to `glm-5`.

### Fixed (Hub v0.7.0)
- **Hub dashboard output duplication**: `agent_output` SSE broadcast payload now includes the server-assigned row ID (`id: row.id`). The frontend SSE handler uses this ID directly instead of generating a throwaway `live-*` ID, so the polling deduplication check correctly suppresses the same line when it arrives via the 2-second poll.

---

## [0.12.0] - 2026-03-30

### Added (CLI)
- **Claude-proxy agent support** (`agentweave agent configure <name> --runner claude_proxy`): run Minimax, GLM, and any OpenAI-compatible model through the Claude Code CLI by injecting `ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY` at subprocess level. API keys are never stored — only the env var name is recorded in `session.json`.
- **`agentweave switch <agent>`**: outputs eval-able `export KEY=VALUE` lines to activate a proxy agent in the current shell (`eval $(agentweave switch minimax)`).
- **`agentweave run --agent <name>`**: resolves env vars, builds relay prompt, and launches the Claude subprocess with env overrides — full one-command delegation to a proxy agent.
- **`agentweave relay --run` flag**: combines relay-prompt generation and immediate subprocess execution.
- **`agentweave agent set-session <name> <id>`**: manually register a Claude `--resume` session ID for per-agent conversation continuity.
- **`agentweave agent set-model <name> <model>`**: update the model name for a claude_proxy agent without reconfiguring all env vars.
- **Built-in provider registry** (`CLAUDE_PROXY_PROVIDERS`): minimax and glm ship with default base URLs, api-key-var names, and model names — `agentweave agent configure minimax` works with zero flags.
- **`src/agentweave/runner.py`** (new): shared helpers (`get_agent_env`, `build_claude_proxy_cmd`, `get_claude_session_id`, `save_claude_session_id`) used by both CLI and watchdog to avoid duplicating env-resolution logic.
- **Watchdog env-var injection**: claude_proxy agents are auto-pinged with `ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY` injected into the subprocess environment — watchdog works for proxy agents without any manual steps.
- **`agentweave reply` guard**: passing a `msg-...` message ID now prints a clear error directing to `send_message` MCP tool instead of silently returning HTTP 405.
- **MCP protocol enforcement in context templates**: all agent context files (`claude_context.md`, `kimi_context.md`, `collab_protocol.md`, `ai_context.md`) now explicitly forbid `agentweave relay`/`agentweave quick` when MCP tools are available and document all three runner types as watchdog-handled.
- **`testrun/setup.sh`**: new test environment setup script; automatically injects `fastmcp` into the agentweave-ai pipx venv so `agentweave-mcp` starts correctly.
- `docs/kimi-task-hub-mcp-minimax-glm.md`: implementation brief for Hub-side proxy agent changes (used for cross-agent delegation).

### Added (Hub v0.6.0)
- **`runner` field in `AgentSummary`** (`hub/hub/schemas/agents.py`, `hub/hub/api/v1/agents.py`): `GET /api/v1/agents` now returns each agent's runner type (`native` / `claude_proxy` / `manual`) read from the synced `session.json`.
- **`get_agent_config` MCP tool** (11th tool in `hub/hub/mcp_server.py`): agents can query a peer's runner type, base URL, and API key env var name via MCP — enabling orchestrators to understand proxy agents.
- **Runner badge in `AgentCard`** (`hub/ui/src/components/agents/AgentCard.tsx`): dashboard shows amber "proxy" badge for `claude_proxy` agents and grey "manual" badge for manual agents — native agents show no badge.
- **Proxy and manual warnings in trigger panel** (`hub/ui/src/components/agents/AgentMessageSender.tsx`): amber warning for claude_proxy agents (env vars must be set on host watchdog); grey info banner for manual agents (no automation, requires human action).
- **`runner` field in TypeScript `AgentSummary`** (`hub/ui/src/api/agents.ts`): UI type matches API response.

---

## [0.11.0] - 2026-03-30

### Changed (CLI)
- **Logging migrated to Python `logging` stdlib**: replaced custom `log_event()` with two handlers — `JSONRotatingFileHandler` (writes same JSONL schema to `events.jsonl`, now with 10 MB rotation / 5 backups) and `HubHandler` (forwards INFO/WARNING/ERROR to Hub when HTTP transport active). Resolves file growth, missing stack traces, and absence of logger hierarchy.
- **`push_log()` added to `BaseTransport` as a no-op default**: removes latent `AttributeError` risk on LocalTransport and GitTransport.
- **`_configure_logging()` called at CLI and watchdog startup**: respects `AW_LOG_LEVEL` (default `WARNING`) and `AW_LOG_FILE` env vars for developer tracing.
- `eventlog.py` retains read-path utilities (`get_events`, `format_event`, `write_heartbeat`, `get_heartbeat_age`) — `agentweave log` output is unchanged.

### Added (CLI)
- `docs/logging-guide.md`: comprehensive developer reference covering logging architecture, migration rationale, and per-module log points for CLI and Hub.

### Added (Hub v0.5.0)
- Hub Docker build and `publish.yml` tag filter fix from v0.10.0 release cycle now included in Hub image.

---

## [0.10.0] - 2026-03-27

### Added (CLI)
- **Yolo mode** (`agentweave yolo --agent <name> --enable/--disable`): per-agent flag to suppress confirmation prompts, enabling fully autonomous agent loops
- **Session sync to Hub**: `session.json` is automatically pushed to the Hub on every save and on watchdog startup — agents appear in the dashboard without manual configuration
- **`push_session()` in HTTP transport**: new method that POSTs session data to `/api/v1/session/sync` endpoint

### Added (Hub v0.4.0)
- **`ProjectSession` table**: stores synced session data (one row per project, upserted on each sync) — agents and their roles are now derived from the session rather than a manual agent list
- **Session sync endpoint** (`POST /api/v1/session/sync`): upserts session data from CLI; called automatically by the watchdog
- **Agent role and yolo fields** in `AgentSummary` schema: `role` (`principal` | `delegate` | `collaborator`) and `yolo` (bool) now surfaced in agent cards
- **Session-based agent discovery**: agents page reads from `ProjectSession` DB table (falls back to filesystem `session.json`) — eliminates need for manual agent configuration

### Removed (Hub)
- **Agent Configurator UI** (`AgentConfigurator.tsx`) and associated manual `/configure` endpoints — replaced by automatic session sync

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
