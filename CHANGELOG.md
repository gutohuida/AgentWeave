# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---
## [0.40.0] - 2026-07-20

### Added (CLI)
- **Seven AI-native agent roles.** Added function-first roles alongside the existing 13 human-title roles: `coordinator` (orchestrate/decompose/delegate in parallel), `model_router` (route each task to the best agent/model by difficulty × capability × cost, with a cheap-first cascade), `explorer` (reconnaissance, condensed cited findings), `implementer` (stack-agnostic executor), `verifier` (evidence-gated evaluation — never open-ended "reflect and revise"), `guardian` (AI-specific safety: slopsquatting, prompt injection, over-broad scopes, secrets), and `context_keeper` (curate shared memory, fight context rot). These reflect where multi-agent frameworks and research have converged — roles named by cognitive function rather than job title — and fill gaps (model routing, long-session memory) that no human-title role covers. All ship with empty `_default_for`, so existing agent defaults are unchanged; the 13 human-title roles remain fully supported and can be combined with the new roles (e.g. `implementer` + `frontend_dev`).

### Changed (CLI)
- **`VALID_ROLE_IDS` consolidated to a single source of truth.** The role-ID list is now defined once in `constants.py` and re-exported from `roles.py`, removing the prior duplication that had to be kept in sync by hand.

### Added (Hub v0.33.0)
- **Native Hub mode support.** Companion Hub-side changes for `agentweave hub start --native`: `uvicorn`-based start/stop/status lifecycle, bootstrap `.env` scaffolding with a generated API key, and Alembic migrations run automatically on first start.
- **Hub-aware CLI transport routing.** Hub REST endpoints now back the CLI's `task`/`agents`/`question`/`msg` commands so tasks and messages created via the CLI are visible in the Hub dashboard.
- **Hub PyPI packaging workflow.** `publish.yml` gained a `publish-hub` job (triggered on `hub-v*` tags) that builds the React UI, bundles it with Alembic migrations into the wheel, and publishes `agentweave-hub` to PyPI.

---
## [0.39.0] - 2026-07-02

### Added (CLI)
- **Native Hub mode (no Docker).** `agentweave hub start --native` runs the Hub via `uvicorn` without Docker: scaffolds `~/.agentweave/hub/.env` with a generated API key on first run, runs Alembic migrations, and manages a cross-platform PID file for the start/stop/status lifecycle. `--no-detach` runs in the foreground for development. The Docker path now suggests `--native` when Docker is unavailable.
- **GitHub Copilot CLI runner.** New `copilot` runner type with JSONL (`--output-format json`) stdout parsing, UUID session resume (`--resume=<uuid>`), auth-failure detection, and CLI-based MCP registration. `AGENT_RUNNER_DEFAULTS["copilot"]` now defaults to the `copilot` runner (previously `manual`).
- **Hub-aware CLI.** `task create/list/show/update` now route through the active transport layer, so tasks created via the CLI are visible to the Hub (previously local-filesystem only). Added `--json` output to `inbox`, `task`, and `agents`; new `agentweave agents list`, `agentweave question ask/get`, and `agentweave msg peek` commands.
- **`hub_client` config (`auto`/`cli`/`mcp`).** Session- and per-agent-level setting that lets the watchdog ping agents with CLI commands (`agentweave inbox --mark-read`) instead of MCP tool calls, so any agent type works in MCP-restricted environments.
- **Comprehensive `agentweave.yml` template on `init`.** Fully commented reference covering every runner, plus `jobs`, `quality`, and `opencode` sections; no longer requires `pyyaml` at generation time.
- **Hub PyPI packaging.** `publish.yml` gains a `publish-hub` job (on `hub-v*` tags) that builds the UI, packages migrations + static UI into the wheel, and publishes `agentweave-hub` to PyPI.
- **Documented Copilot CLI model selection.** The `copilot` runner already forwarded a configured `model` (e.g. `claude-opus-4.5`, `claude-sonnet-4-5`) via `--model`; the `agentweave.yml` template now shows this with an example, and `_agent_ping_cmd` gained dedicated test coverage for the flag alongside `--yolo`/`--allow-all-tools` and `--resume=<uuid>`.

### Security (CLI)
- **Native Hub now binds to `127.0.0.1` instead of `0.0.0.0`.** Binding to all interfaces exposed the unauthenticated `GET /api/v1/setup/token` endpoint — which returns the bootstrap API key and gates only on RFC1918 source IPs (all of `10/8` and `172.16-31`) — to other hosts on a corporate LAN. Loopback binding closes this without affecting same-machine CLI discovery or the Docker deployment.
- **Native `.env` is written `0600` on POSIX.** The scaffolded `~/.agentweave/hub/.env` holds the bootstrap API key and ticket secret; it was previously created world-readable (umask default). Now restricted to the owner, matching the existing `transport.json` handling.

### Fixed (CLI)
- **`agentweave inbox` is read-only by default again.** The unreleased default of marking every message read (and, with no `--agent`, draining *all* agents' inboxes) could silently consume messages before their target agent processed them. Marking-as-read now requires an explicit `--mark-read`; the watchdog CLI-mode prompt already passes it.
- **Concurrent Copilot agents with PAT auth.** The `spawn_runner_copilot` serialization lock (needed only for the Windows Credential Manager OAuth race) is now skipped when a PAT (`COPILOT_GITHUB_TOKEN`/`GH_TOKEN`/`GITHUB_TOKEN`) is configured, allowing full concurrency. OAuth users remain serialized.
- **`hub stop`/`hub destroy` no longer risk killing an unrelated process.** After an OS PID recycle the stored PID could belong to a bystander; the native stop/destroy paths now confirm the Hub is actually serving on the recorded port before terminating, and otherwise just clear the stale PID file.
- **Orphaned `uvicorn` on failed native startup.** When the startup health check times out, the spawned process is now terminated instead of being left to linger and bind the port with no PID file to track it.
- **Invalid `agentweave.yml` for names with backslashes/newlines.** The generator only escaped double quotes; a project name containing a Windows path or newline produced a file that failed to parse. Backslashes, quotes, and control characters are now escaped.

---
## [0.38.1] - 2026-06-18

### Fixed (CLI)
- **Python 3.8 compatibility.** Added `from __future__ import annotations` to `src/agentweave/cli.py` and `src/agentweave/watchdog.py` so PEP 585 generic type syntax (`list[...]`, `dict[...]`, `tuple[...]`, `set[...]`) does not fail at runtime on Python 3.8.
- **macOS CI failure.** Changed `tests/test_cli_watch.py::test_cmd_start_does_not_leak_fd_on_posix` to Linux-only; it relies on `/proc/<pid>/fd`, which is not available on macOS.
- **Lint configuration.** Added `UP006` and `UP037` to the ruff ignore list so the new `__future__` annotations do not force a wholesale typing-style rewrite.

---
## [0.38.0] / [Hub 0.32.0] - 2026-06-18

### Fixed (CLI v0.38.0)
- **SPA API key leak (PR 1 / C1).** Removed the code path that injected the live project API key into the Hub single-page-app HTML response.
- **GitTransport data-loss paths (PR 2).** Abort push when `ls-tree` fails after `ls-remote` succeeded; add a local outbox for at-least-once delivery on push failure.
- **GitTransport reliability (PR 2).** Add `subprocess.run(timeout=30)` to all `_run_git` calls; wrap seen-set operations in `lock()` to prevent races; restructure status-update filename parsing; add microsecond precision to `_iso_compact`.
- **HttpTransport data-loss paths (PR 2).** Retry 5xx/429/`URLError` with exponential backoff and honor `Retry-After`; catch `JSONDecodeError` and classify as `hub_invalid_response`; add `timeout=10` to `urllib.request.urlopen` in the MCP server.
- **Atomic archive/move operations (PR 3).** Use `os.replace` and `lock()` for archive operations in local transport and messaging; atomic move-to-completed for task operations.
- **File permissions and response safety (PR 3).** Set POSIX 0600 permissions when writing message/task files; truncate and redact `api_key=` from Hub error bodies; cap Hub response bodies at 10 MB.
- **UTC-aware datetimes (PR 4).** Replaced `datetime.utcnow()` with `datetime.now(timezone.utc)` across CLI, watchdog, and MCP server; standardized heartbeat parsing in `eventlog.py` so malformed lines are logged, not swallowed.
- **Subprocess timeouts and encoding (PR 4).** Added `encoding="utf-8", errors="replace"` to `Popen(text=True)` in watchdog; added `timeout=` to all `subprocess.run` calls in CLI.
- **Atomic `transport.json` write and SHA256 verification (PR 4).** `transport.json` is now written atomically with `chmod 600` on POSIX; downloaded compose/`.env` files are verified against embedded SHA256 checksums.
- **Dead code removal (PR 8).** Deleted 277 lines of unreachable `_build_agent_context` implementation in `cli.py` and `watchdog.py` and removed the duplicate `_load_dotenv` in watchdog.
- **Code quality sweep (PR 11).** Standardized CLI output on print/logging helpers; standardized `Optional[X]` types; split `cmd_init` and `_do_run_agent_subprocess` into helpers under 50 lines each.
- **UUID length (PR 11).** `utils.generate_id` now uses full 32-char UUID4 by default with an optional `uuid_length` parameter.

### Fixed (Hub v0.32.0)
- **Input validation hardening (PR 5).** Role IDs in `/agents/context` are now validated against `^[a-zA-Z0-9_-]{1,64}$` to block path-traversal reads of arbitrary files (S1).
- **Create schemas no longer accept client-supplied IDs or timestamps.** Removed `id`/`timestamp` from `MessageCreate`, `id`/`created_at` from `TaskCreate`, and `id` from `JobCreate`; extra fields are rejected (S5).
- **String length caps added to all Hub schemas.** Agent names, IDs, subjects, titles, and content now enforce `max_length` limits (256 for names/subjects, 10,000 for content, 128 for IDs, etc.) (S6).
- **`/agent/trigger` rejects unsafe `work_dir` values.** Paths containing `..`, `~`, or non-printable characters now return HTTP 400 (S12).
- **`/agent/{agent}/chat` query `limit` is bounded.** Accepts values from 1 to 500 inclusive (M14).
- **`/agents/{name}/register-session` rejects configured-agent name collisions**, matching the existing `register_agent` guard (M16).
- **SSE no longer accepts raw API keys in `?token=`.** All non-SSE endpoints now require the API key in the `Authorization` header. The SSE stream accepts only short-lived signed tickets from the new `/api/v1/events/ticket` endpoint (S3).
- **`list_agents` no longer issues per-agent queries.** Latest heartbeat, message count, active task count, context usage, and session start are now fetched in bulk, eliminating the N+1 query pattern (M15).
- **`update_task` MCP tool no longer sends an unused `agent` parameter** to the REST API (M17).
- **Request body size capped at 1 MB.** A middleware layer returns HTTP 413 for oversized POST bodies before they reach route handlers (bonus).
- **DB migrations run automatically on startup (PR 7 / H5).** `init_db` now invokes `alembic upgrade head` after `Base.metadata.create_all`, wrapped in try/except so dev mode (in-memory SQLite, missing alembic.ini) still works. Closes H5: a deployment that only runs `init_db` no longer misses schema changes that live in Alembic migrations. The alembic command is run in a worker thread so its internal `asyncio.run()` doesn't conflict with the FastAPI lifespan's event loop.
- **`job_runs.error_summary` capped to `String(500)` (PR 7 / DB-4).** Was unbounded `Text` — could grow without limit if a job captured a full agent stack trace. Migration 0007 was edited to use `String(500)` for fresh installs, and migration 0008 alters existing deployments where 0007 already added the column as `Text`.
- **Hub UI security hardening (PR 9).** `useSSE` streams via `fetch()` with `Authorization: Bearer` header (no `?token=` in URL); `configStore` stores API key in `sessionStorage` and only theme/mode in `localStorage`; `ActivityLog` uses ref-synced pause flag; `NEW_SESSION_ID` is a shared constant; added `<ErrorBoundary>` at the App root.
- **Hub UI performance and deduplication (PR 10).** Replaced unconditional 2s output polling with SSE-driven polling; extracted shared agent-status helpers to `lib/agentStatus.tsx`; extracted `<SidebarItem>` component; rewrote `App.tsx` routing as a `PAGES` map that mounts only the active page.

### Added (CLI v0.38.0)
- **Test coverage sweep (PR 12).** +108 tests across CLI and Hub: `tests/test_logging_handlers.py`, `tests/test_runner.py`, enhanced `test_eventlog.py`, `test_locking.py`, `test_http_transport.py`, `test_transport_git.py`; `hub/tests/test_jobs_crud.py`, `hub/tests/test_agent_chat.py`, expanded `hub/tests/test_mcp_server.py`.

### Added (Hub v0.32.0)
- **First Hub UI tests (PR 9).** Vitest + jsdom + Testing Library suite covering SSE auth, config storage, ActivityLog refs, constants, and ErrorBoundary.
- **UI deduplication tests (PR 10).** 41 new vitest tests for `agentStatus`, `SidebarItem`, App mounting, and SSE-only polling.
- **Regression tests in `hub/tests/test_agents.py`** and additions to `hub/tests/test_messages.py`, `hub/tests/test_tasks.py`, and `hub/tests/test_jobs.py` covering the PR 5 validation rules.
- **New `hub/tests/test_bola.py`** multi-tenant isolation test: creates two projects with separate API keys and verifies Project B cannot read Project A's resources on every endpoint (T5).
- **`hub/tests/test_auth.py` additions** for the SSE ticket flow, query-token rejection on REST endpoints, and the 1 MB body-size cap.
- **New `hub/tests/test_migrations.py`** covering migration model types, value-length boundary, fresh-DB alembic round-trip, migration 0008 column alter, `init_db` alembic behavior, and graceful alembic failures.

---
## [0.37.1] - 2026-06-14

### Added (CLI)
- **Per-agent opencode CLI override.** New `AgentConfig.cli` field lets operators pin a specific opencode binary (e.g. an internal build) for a single agent without touching the global path. Falls back to PATH lookup when unset; validated at YAML load time (non-empty string only).
- **Free-form `opencode:` block in `agentweave.yml`.** New top-level section lands verbatim in the generated `opencode.json` (provider, model, env, etc.). Mirrors how teams already share their opencode config.
- **`agentweave.template.yml` and `docs/guides/opencode-models.md`** as documentation/scaffolding for operators.

### Fixed (CLI)
- `test_should_fire_old_last_run` now passes under croniter 6.x (subclasses `datetime.datetime` and honors `tz` in `now()`). The fix is the same change previously shipped on the audit branch as PR 0.5.
- Addressed inherited ruff N806 and mypy no-untyped-def warnings introduced by the opencode commit.

### Changed (Hub v0.31.2)
- Version bumped to v0.31.2 for release parity with CLI v0.37.1. No Hub-specific functional changes in this release.

## [0.31.1] - 2026-05-04

### Fixed (Hub)
- Migration `0007_add_job_run_error_summary` now checks if `job_runs` table exists before altering it. Fixes `sqlite3.OperationalError: no such table: job_runs` on existing databases that predate the `job_runs` table.

## [0.37.0] - 2026-05-04

### Added (CLI)
- New `context_builder.py` module for centralized agent context rendering across CLI, watchdog, Hub, and MCP paths
- Diagnostics v2: context source validation, injection method info, structured health checks for agents and roles
- MCP server exposes `build_agent_context` tool for runtime context generation
- Watchdog context injection with `shared/context.md` (session focus) and mode-aware guidance
- New `aw-spec-technical-explore` skill template for technical deep-dives
- Updated `aw-spec-explore`, `aw-spec-apply`, and `aw-spec-propose` skill templates
- Quality Governance settings surfaced in watchdog prompts when configured

### Added (Hub v0.31.0)
- Agent self-registration endpoint with role resolution and project config support
- Enhanced agent management API with bundled roles fallback and structured responses
- Tests for self-registered agents and runtime diagnostics

### Fixed
- CI failures: pilot mode message separation, test isolation with unique agent names, mypy type errors, ruff lint

## [0.36.0] - 2026-04-29

### Added (CLI)
- New `agentweave doctor` command — runs runtime readiness diagnostics covering session state, transport config, watchdog health, agent context files, and Hub connectivity
- New `src/agentweave/diagnostics.py` module (stdlib-only, zero new dependencies) with secret-redacting checks and structured `DiagnosticResult` output
- Watchdog agent prompts now prepend `shared/context.md` (session focus) and inject Hub/MCP mode guidance, explicitly forbidding CLI relay commands when Hub is active
- Quality Governance settings surfaced in watchdog prompts when configured
- HTTP transport: new `HubTransportError` exception class and structured error helpers

### Added (Hub v0.30.0)
- Job runs now capture and store redacted `error_summary` on failure (new DB column via migration 0007)
- Scheduler fires `job_run_failed` event to the activity log with agent, job, and error context
- New `GET /api/v1/logs/agents` endpoint and per-agent filter on the logs endpoint
- LogsView UI gains an agent filter dropdown; JobCard shows error summaries inline
- Agent trigger endpoint improvements with better diagnostics logging
- Tests for runtime diagnostics (CLI and Hub)

---
## [Hub 0.29.1] - 2026-04-28

### Fixed (Hub v0.29.1)
- Included task-only assignees in the Hub agent list even when a synced session config exists
- Applied Black formatting fixes required by CI

---
## [0.35.0] - 2026-04-28

### Added (CLI)
- Fixed context file paths to use `as_posix()` for codex/opencode launch commands
- Synced documentation with latest implementation updates

### Added (Hub v0.29.0)
- Synced documentation with latest implementation updates

---
## [0.34.0] - 2026-04-27

### Added (CLI)
- **Auto-managed `.gitignore`** — `agentweave init` creates or updates `.gitignore` with a managed AgentWeave runtime-state block (tasks, messages, agents, session, transport, logs, watchdog files)
- **Auto-scaffold `.env`** — `agentweave init` creates a `.env` placeholder for provider API keys if one doesn't exist
- **Per-agent model flag** — Runner invocations now pass the configured model via `--model` for runners that support it
- Improved runner display labels in Hub agent list (shows configured model name)
- Expanded test coverage for init, session, watchdog, constants, and CLI commands

### Added (Hub v0.28.0)
- `update_agent_config` MCP tool now supports clearing a model field when set to null
- Hub agent list reflects per-agent runner type and model in display labels

---
## [0.33.0] - 2026-04-26

### Added (CLI)
- **Project-wide instructions** — `agentweave init` creates `.agentweave/project_instructions.md` placeholder for local transport
- `_build_agent_context` now embeds project instructions (from Hub DB or local file) into per-agent context files `.agentweave/context/<agent>.md`
- Updated `claude_context.md`, `kimi_context.md`, and `aw-collab-start` skill templates to guide agents toward `get_context` MCP tool on HTTP transport

### Added (Hub v0.27.0)
- **Project Instructions page** — New Hub UI screen with markdown textarea for editing per-project rules
  - `GET /api/v1/project/instructions` — returns instructions content (empty string if none set)
  - `PUT /api/v1/project/instructions` — upserts instructions in DB
  - `_load_role_content` prepends Hub instructions before role guides with `---` separator
- Instructions content auto-injected into per-agent context files at launch time

### Fixed
- Agents now reliably receive project-wide instructions regardless of transport mode

---
## [0.32.0] - 2026-04-26

### Added (CLI)
- **Codex skills generation on init** — `agentweave init` now auto-generates Codex-specific skills in `.agents/skills/` for seamless Codex CLI integration

### Added (Hub v0.26.0)
- **Complete UI redesign** — Replaced Material Design 3 with Linear/shadcn-style design system
  - New dark/light token system (`--bg`, `--surface`, `--surface-2`, `--border`, `--text`, etc.)
  - Inter + JetBrains Mono fonts via Google Fonts CDN
  - New 220px labeled sidebar with grouped sections (WORK, COMMUNICATION, OBSERVE)
  - **Overview page** — New default landing page with agent health grid, task summary chips, and activity ticker
  - **Agents page** — Two-panel layout replacing Agents + MissionControl with AgentDetailPanel (Output/Tasks/Messages/Info tabs)
  - **QuestionInterruptCard** — Persistent amber interrupt card for unanswered questions
  - **7-column kanban board** — Added `revision_needed` column; collapsible rejected section; agent filter chips
  - **TaskCard expand/collapse** — Click to reveal full task details (description, requirements, acceptance criteria)
  - Semantic badge color system with rgba tints
  - Agent cards with status pulse dots and context usage bars
  - Grid view toggle for agent cards
  - Compact/Reset session buttons in agent detail header

### Removed
- **MissionControlPage** — Replaced by OverviewPage + unified AgentsPage

---
## [0.31.0] - 2026-04-25

### Added (CLI)
- **Codex runner support** — Full support for OpenAI Codex as an AgentWeave runner
  - Headless execution via `codex exec --json` with JSONL output parsing
  - Thread-based session resumption (`codex exec resume <thread_id>`)
  - Context file injection via `-c model_instructions_file=<path>`
  - Model selection via `--model` flag
  - Memory mode control via `runner_options.memory`
  - Auto-approval bypass when `yolo: true` (`--dangerously-bypass-approvals-and-sandbox`)
  - Context usage monitoring with model-aware token limits
  - Hub UI badge and Mission Control integration
- `runner_options` per-agent configuration in `agentweave.yml`
- Data-driven JSONL session ID extraction (`session_id_field`, `session_event_type`)

### Added (Hub v0.25.0)
- `runner_options` exposed in `AgentSummary` schema and API
- SSE broadcast for `new_session_request` events

### Fixed
- Codex parser handles actual `item.started` / `item.completed` event types
- Run Codex from `.codex-run/` subdir to avoid bootstrap mode while preserving MCP transport discovery
- Absolute context file paths for neutral cwd execution

---
## [0.30.0] - 2026-04-25

### Added (CLI)
- **OpenCode agent support** — New runner type for the OpenCode terminal-based AI coding agent
  - Stable session IDs (`agentweave-{agent}`)
  - File-based MCP registration via auto-generated `opencode.json`
  - Context file injection via `--file` flag
  - Model selection via `--model` flag

---
## [0.29.0] - 2026-04-21

### Added (CLI v0.29.0 / Hub v0.24.0)
- **Auto-mark as read** — `get_inbox()` now automatically archives messages after returning them. Agents no longer need to call `mark_read()` separately in either local or Hub MCP mode.

---
## [0.28.0] - 2026-04-20

### Added (CLI v0.28.0 / Hub v0.23.0)
- **Quality governance framework** — Configurable quality controls via `agentweave.yml`: `review_required`, `docs_threshold`, `echo_chamber_guard`, `attribution_tag`, `dependency_check`
- **QualityConfig** — New dataclass in `config.py` with validation and serialization
- **Hub UI Quality Health panel** — Real-time quality metrics dashboard
- **aw-verify skill** — Structured zero-trust quality review for completed tasks
- **code_decision.md template** — Standardized documentation for AI-generated changes
- **Updated role guides** — All roles now include quality governance awareness
- **Updated skills** — All skills reference quality checks and decision documentation

### Fixed (CLI v0.28.0)
- **CI reliability** — Updated codecov action to v4, added `fail-fast: false` to test matrix
- **MCP test compatibility** — Skip MCP server tests when `fastmcp` is unavailable

---
## [0.27.0] - 2026-04-20

### Added (CLI v0.27.0 / Hub v0.22.0)
- **Agent self-registration** — External agents can join a session dynamically via `register_agent(name, contact_mode)` MCP tool without being pre-declared in `agentweave.yml`
- **Config parity for self-registered agents** — Self-registered agents can store full configuration (`runner`, `model`, `roles`, `yolo`) in a JSON blob, making them indistinguishable from configured agents in the Hub UI
- **PATCH /api/v1/agents/{name}** — Partial config updates for self-registered agents without re-registration
- **MCP tools** — New `register_agent`, `get_context`, `heartbeat`, and `update_agent_config` tools on both CLI and Hub MCP servers
- **Role template bundling** — Hub Docker image now bundles built-in role templates so `get_context` works even when the CLI package isn't installed
- **Liveness indicators** — Hub UI shows online/offline dots for self-registered agents based on heartbeat age
- **Watchdog guards** — Self-registered `poll` agents are skipped by the watchdog for job firing and message triggers

### Fixed (CLI v0.27.0 / Hub v0.22.0)
- **Cross-package import** — Removed `from agentweave.constants import CONTACT_MODES` from Hub code that caused 500 errors in Docker
- **`spawn_cmd` type mismatch** — Aligned Hub MCP `spawn_cmd` type with CLI (`List[str]`)

### Database
- Migration `0005` — Adds `contact_mode`, `self_registered`, `mcp_endpoint`, `spawn_cmd` to `agents` table
- Migration `0006` — Adds `config` JSON column to `agents` table

## [0.26.0] - 2026-04-14

### Added (CLI v0.26.0)
- **`.env` file auto-loading** — AgentWeave now automatically loads a `.env` file from the project root. This makes `claude_proxy` agents (MiniMax, GLM, etc.) work out of the box without manually exporting API keys in the shell. Shell-exported variables still take precedence.
- **Code formatting** — Applied `black` formatting fixes across the codebase.

## [0.25.0] - 2026-04-14

### Added (CLI v0.25.0)
- **`principal` field in `agentweave.yml`** — Declare the principal agent explicitly with `principal: true`
- **Roles reconciliation during activate** — `roles.json` is now cleaned of ghost agents and synced to the Hub automatically

### Fixed (CLI v0.25.0)
- **Principal agent metadata** — `session.set_principal()` now updates both the top-level principal and the per-agent `role` entry, fixing incorrect "delegate" display in the Hub
- **Role persistence** — `agentweave activate` now correctly saves role assignments and copies missing role definitions into `roles.json`

## [0.24.0] - 2026-04-14

### Added (CLI v0.24.0)
- **Activate improvements** — Auto-remove orphaned agents, print explicit Hub sync feedback, and show pilot agent run commands
- **Encoding fixes** — Always use UTF-8 for file reads on Windows
- **Python 3.8 compatibility** — Use `typing.Tuple` instead of `tuple[]`
- **Documentation** — Updated README and docs for `agentweave.yml` workflow, added missing pages to mkdocs nav

### Added (Hub v0.20.0)
- **SPA auto-config** — Inject live API key from database into dashboard `window.__AW_CONFIG__`
- **Session sync cleanup** — Delete orphaned `Agent` rows when agents are removed from session sync

### Fixed (CLI v0.24.0)
- **Code quality** — Fixed mypy type errors, added missing dev dependencies, applied black formatting


## [0.23.0] - 2026-04-13

### Added (CLI v0.23.0)
- **Declarative configuration (`agentweave.yml`)** — New YAML-based project configuration with `agentweave activate` command
- **`python -m agentweave` support** — Added `__main__.py` for module execution
- **Documentation** — Added migration guide and `agentweave.yml` reference documentation
- **Session management improvements** — Updated session and watchdog for new config flow

### Added (Hub v0.19.0)
- **Setup API** — New `/api/v1/setup` endpoints for Hub initialization tokens

### Fixed (CLI v0.23.0)
- **Lint and code quality** — Fixed ruff issues across `cli.py`, `config.py`, and `session.py`

## [0.22.0] - 2026-04-12

### Added (CLI v0.22.0 / Hub v0.18.0)
- **Documentation and Skill Template Updates** — Enhanced user guides and AI skills:
  - New pilot mode documentation with detailed setup and usage guides
  - New AI jobs guide for scheduling recurring agent tasks
  - Updated CLI command reference with new `--agent-file` and session management options
  - Enhanced Hub API documentation with new endpoints
  - Improved skill templates for explore, propose, and team workflows
  - Added watchdog architecture documentation

### Fixed (CLI v0.22.0)
- **BaseTransport compatibility** — Added `register_session` method to BaseTransport ABC for mypy compatibility
- **Code formatting** — Applied black 26.x formatting fixes across the codebase

## [0.21.0] - 2026-04-12

### Added (CLI v0.21.0 / Hub v0.17.0)
- **Pilot Mode for Agent Session Management** — New feature for managing long-running agent sessions:
  - Hub DB `agents` table with `pilot` flag and `registered_session_id` (migration 0004)
  - CLI `session-register` command for registering pilot agents with session IDs
  - Auto-generation of kimi `--agent-file` YAML for seamless pilot mode integration
  - Watchdog pilot mode handling for file monitoring and process management
  - Hub UI updates to display pilot status and session information in AgentInfoTab
  - New MCP tools: `register_session`, `get_agent_config`
  - API endpoints for agent CRUD and session registration

## [0.20.1] - 2026-04-09

### Fixed (CLI v0.20.1)
- **YAML parse error in auto-generated context** — Fixed `_build_agent_context` generating `*` at column 1 (YAML alias marker) which crashed Kimi Code when parsing `--agent-file`
- **Removed unwanted checkpoint nudge** — Removed automatic checkpoint reminder messages after every 20 messages; use `/aw-checkpoint` skill or SSE events instead

### Added (Hub v0.16.0)
- **AI Jobs (Scheduled Tasks)** — New feature for scheduling recurring agent tasks:
  - Create jobs with cron expressions to trigger agents automatically
  - Jobs can start new sessions or resume existing ones
  - Job run history tracking with automatic pruning
  - New API endpoints: `/api/v1/jobs`, `/api/v1/jobs/{id}/run`, `/api/v1/jobs/{id}/toggle`
  - New React components: `JobsPage`, `JobCard`, `JobForm`, `JobHistoryPanel`
  - New MCP tools: `create_job`, `list_jobs`, `get_job`, `toggle_job`, `delete_job`, `run_job`

### Fixed (Hub v0.16.0)
- **Cron auto-run not working** — Fixed APScheduler job store pickling issue where bound methods holding event loops couldn't be serialized; jobs now auto-fire correctly at scheduled times

## [0.20.0] - 2026-04-09

### Added (CLI v0.20.0)
- **Agent pause/resume functionality** — agents can now be paused and resumed via API and CLI
- **Session mission control** — new watchdog session management features for better multi-session handling
- **Enhanced HTTP transport** — improved transport layer with better error handling
- **New agent state constants** — added `AGENT_STATE_PAUSED` and related state management constants

### Added (Hub v0.15.0)
- **Mission Control dashboard enhancements** — improved agent management UI with pause/resume controls
- **Agent state API endpoints** — new endpoints for managing agent paused/active states
- **UI improvements** — updated MissionControlPage with better agent status visualization

## [0.19.0] - 2026-04-07

### Added (CLI)
- **AW-Spec workflow skill templates** — 4 new skills for structured change management:
  - `/aw-spec-explore` — explore an idea and generate structured findings
  - `/aw-spec-propose` — create a structured proposal with design and tasks
  - `/aw-spec-apply` — implement a proposal with optional agent delegation
  - `/aw-spec-archive` — archive completed proposals
- **Documentation updates** — comprehensive docs for multi-role agents, new MCP tools, and dashboard features
- **Watchdog session handling fix** — fixed direct-trigger session persistence with [NewSession] marker

### Added (Hub v0.14.0)
- **Code quality improvements** — black 26.x formatting compatibility fixes

## [0.18.0] - 2026-04-05

### Added (CLI)
- **OpenSpec workflow skill templates** — 4 new skills for structured change management:
  - `aw-spec-explore` — explore an idea and generate structured findings
  - `aw-spec-propose` — create a structured proposal with design and tasks
  - `aw-spec-apply` — implement a proposal with optional agent delegation
  - `aw-spec-archive` — archive completed proposals

### Added (Hub v0.12.0)
- Code quality improvements — black formatting fixes across Hub and CLI



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


## [0.13.0] - 2026-03-31

### Fixed (CLI)
- **Watchdog output duplication**: `_parse_claude_stream_line` was emitting the `result` field from the final `result`-type JSONL message, which is a full copy of the already-streamed assistant response. The field is now ignored; only the cost line is emitted from `result` messages.
- **GLM provider config** (`CLAUDE_PROXY_PROVIDERS`): switched GLM base URL from `/paas/v4` (OpenAI-compatible) to `/anthropic` (Anthropic-compatible) and upgraded default model from `glm-4` to `glm-5`.

### Fixed (Hub v0.7.0)
- **Hub dashboard output duplication**: `agent_output` SSE broadcast payload now includes the server-assigned row ID (`id: row.id`). The frontend SSE handler uses this ID directly instead of generating a throwaway `live-*` ID, so the polling deduplication check correctly suppresses the same line when it arrives via the 2-second poll.


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


## [0.6.1] - 2026-03-21

### Added (Hub UI v0.2.1)
- **Expandable TaskCard**: tasks now expand inline to show requirements, acceptance criteria, deliverables, and notes
- **Expandable MessageCard**: long messages truncate with click-to-expand; message type and task ID chips in footer; subject shown as a labelled field
- Task interface extended with `assigner`, `requirements`, `acceptance_criteria`, `deliverables`, `notes` fields
- Assigner badge shown on task cards when assigner differs from assignee

### Fixed (Hub)
- `questions.py`: reply message sender changed from `"human"` to `"user"` for consistency with message schema


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


## [Unreleased]

### Planned
- Web dashboard for visualizing collaboration
- Desktop notifications
- Slack/Discord integration
- Additional agent profiles
- Plugin system
- VS Code extension


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
