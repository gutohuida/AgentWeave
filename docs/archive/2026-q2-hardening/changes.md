# Detailed changes — 2026 Q2 Hardening Release

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
- **DB migrations run automatically on startup (PR 7 / H5).** `init_db` now invokes `alembic upgrade head` after `Base.metadata.create_all`, wrapped in try/except so dev mode still works.
- **`job_runs.error_summary` capped to `String(500)` (PR 7 / DB-4).** Migration 0007 was edited for fresh installs, and migration 0008 alters existing deployments where 0007 already added the column as `Text`.
- **Hub UI security hardening (PR 9).** `useSSE` streams via `fetch()` with `Authorization: Bearer` header; `configStore` stores API key in `sessionStorage` and only theme/mode in `localStorage`; `ActivityLog` uses ref-synced pause flag; `NEW_SESSION_ID` is a shared constant; added `<ErrorBoundary>` at the App root.
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
