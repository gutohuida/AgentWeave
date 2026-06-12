# PR Roadmap — 12-PR Execution Plan

Each PR is independently shippable. Burnout-safe: stop after any PR and the codebase still works. Test-first on every fix.

## Conventions for all PRs

1. **Branch:** All work happens on `audit/2026-q2-hardening`.
2. **Test-first:** For CRITICAL and HIGH issues, write a failing test that demonstrates the bug. Confirm it fails. Then apply the fix. Confirm it passes. This is non-negotiable for security and data-loss fixes.
3. **No public API changes:** The user-facing CLI commands, Hub API endpoints, and Hub UI surface stay the same. All changes are internal hardening.
4. **Commit message format:** `<type>(<scope>): <description>` with a body explaining the bug, the fix, and the test.
5. **Lint clean:** `ruff check src/`, `black src/`, `mypy src/` must pass.
6. **All tests green:** `pytest tests/ -v` (CLI) and `cd hub && pytest tests/ -v` (Hub) must pass.
7. **Update CHANGELOG.md** with a one-line entry per fix.

## Pacing

At 10-20 hrs/week, with test-first on every fix:

| Week | PRs |
|---|---|
| 1 | PR 1, PR 2 (start) |
| 2 | PR 2 (finish), PR 3 |
| 3 | PR 4, PR 5 |
| 4 | PR 6, PR 7 |
| 5 | PR 8, PR 9 (start) |
| 6 | PR 9 (finish), PR 10 |
| 7 | PR 11, PR 12 (start) |
| 8 | PR 12 (finish) |
| 9 | **Tag v0.38.0, merge to master** |

Total: 8-9 weeks, 12 PRs, 1 release.

---

## PR 1 — CRITICAL: SPA key leak fix

**Closes:** C1
**File changes:** 4 files, 1 new file
**Test:** 2 new tests in `hub/tests/test_setup.py`
**Risk:** Low — only removes a code path, doesn't add new logic
**Time:** 0.5 day

See `pr1-spa-key-leak.md` for full details.

---

## PR 2 — Transport data-loss bugs

**Closes:** H1, H2, H3, M7, M11, M12, M13, M23
**File changes:** `src/agentweave/transport/git.py`, `src/agentweave/transport/http.py`
**Test:** New `tests/test_transport_git.py` (20+ tests), new HTTP retry tests in `tests/test_http_transport.py`
**Risk:** Medium — touches the most critical layer
**Time:** 3-4 days

### Changes

1. **H1** — `git.py:130-139`: Abort push when `ls-tree` fails after `ls-remote` succeeded. Add a proper "branch doesn't exist" detection that doesn't conflate with "ls-tree errored."
2. **H2** — `git.py:166-176`: Add a local outbox at `.agentweave/outbox/` — write first, push second, retry on failure.
3. **H3** — `http.py` (new logic): Add retry+backoff for 5xx, 429, `URLError`; honor `Retry-After` header.
4. **H6** — `http.py:97-100`: Catch `json.JSONDecodeError`, raise `HubTransportError(classification="hub_invalid_response")`.
5. **M7** — `git.py:55-65, 92-95`: Add `subprocess.run(timeout=30)` to all `_run_git` calls.
6. **M11** — `git.py:300-302`: Wrap `_get_seen_set` / `_save_seen_set` in `lock(f"git-seen-{agent}")`.
7. **M12** — `git.py:340-352`: Restructure status-update filename to `__status__{new}__{ts}.json` with double-underscore separators.
8. **M13** — `git.py:50-52`: Add microseconds to `_iso_compact`, bump UUID suffix from 6 to 8 hex.
9. **M23** — `mcp_server.py:70`: Add `timeout=10` to `urllib.request.urlopen`.

### Commit message

```
fix(transport): harden data-loss paths in git and http transports

- GitTransport: abort push when ls-tree fails after ls-remote succeeded
  (was silently falling through to a "new branch" path and wiping the
  entire orphan branch).
- GitTransport: add local outbox for at-least-once delivery on push failure.
- HttpTransport: retry 5xx/429/URLError with exponential backoff, honor
  Retry-After header.
- HttpTransport: catch JSONDecodeError, classify as hub_invalid_response.
- GitTransport: add subprocess.run timeout=30 to all _run_git calls.
- GitTransport: wrap seen-set operations in lock() to prevent
  read-modify-write races when two agents share a machine.
- GitTransport: restructure status-update filename parsing to handle
  task_ids that contain digit-prefixed substrings.
- GitTransport: add microsecond precision to _iso_compact.

New tests/test_transport_git.py covers all 20+ critical paths.
Existing tests pass.
```

---

## PR 3 — Transport error handling & safety

**Closes:** H8, M8, M9, M10, S7, S10, S11, S2
**File changes:** `src/agentweave/transport/http.py`, `src/agentweave/transport/local.py`
**Test:** Add to `tests/test_http_transport.py` and `tests/test_transport_local.py`
**Risk:** Medium
**Time:** 2 days

### Changes

1. **H8** — `cli.py:1869-1870`: Use `with open(...)` for the watchdog log file; pass via temp file.
2. **M8, M9** — `local.py:38-53`, `messaging.py:99-119`: Atomic `os.replace` for archive operations; wrap in `lock()`.
3. **M10** — `task.py:172-181`: Atomic move to completed using `os.replace`.
4. **S2** — `messaging.py:78-89`: Add `re.match(r"^[a-zA-Z0-9_-]+$", message_id)` check (defense in depth at the transport boundary).
5. **S7** — `http.py:111-113`: Truncate `body_text` to 200 chars + redact `api_key=` query strings in error messages.
6. **S10** — `http.py`: Add response body size cap (10 MB).
7. **S11** — `local.py`: Set file permissions to 0600 on POSIX when writing message/task files.

---

## PR 4 — CLI security & correctness

**Closes:** M3, M4, M5, M6, M12, S8, S9
**File changes:** `src/agentweave/cli.py`, `src/agentweave/watchdog.py`, `src/agentweave/eventlog.py`, `src/agentweave/mcp/server.py`
**Test:** Add to `tests/test_cli.py`, new `tests/test_eventlog.py`
**Risk:** Low
**Time:** 2-3 days

### Changes

1. **M3** — `cli.py:3514-3515, watchdog.py:495, mcp/server.py:386-387, 773`: Replace `datetime.utcnow()` with `datetime.now(timezone.utc)`.
2. **M4, M6** — `eventlog.py:27-39`: Standardize on UTC-aware everywhere; fix silent heartbeat parse swallow.
3. **M5** — `watchdog.py:2480-2489`: Add `encoding="utf-8", errors="replace"` to `Popen(text=True)`.
4. **M12** — `cli.py:2405, 2312-2322, 4122`: Add `timeout=` to all `subprocess.run` calls.
5. **S8** — `cli.py:2195, 2256, 2874-2876`: Atomic write of `transport.json`; `chmod 600` on POSIX.
6. **S9** — `cli.py:2549, 2558`: Add SHA256 checksum verification for downloaded compose/.env.

---

## PR 5 — Hub input validation

**Closes:** S1, S5, S6, S12, M14, M16
**File changes:** `hub/hub/api/v1/agents.py`, `hub/hub/api/v1/agent_trigger.py`, all `hub/hub/schemas/*.py`
**Test:** Add to `hub/tests/test_agents.py` (new), `hub/tests/test_messages.py`, `hub/tests/test_tasks.py`
**Risk:** Medium — adding input validation can break existing clients
**Time:** 2 days

### Changes

1. **S1** — `agents.py:495-533, 875-890`: Add `re.match(r"^[a-zA-Z0-9_-]{1,64}$", role)` check in `_load_role_content`.
2. **S5** — `schemas/messages.py:19-21, schemas/tasks.py:33-34, schemas/jobs.py:17`: Remove `id`, `timestamp`, `created_at` from Create schemas.
3. **S6** — All schemas: Add `max_length=…` to every `str` field (256 for names/subjects, 10000 for content, 128 for IDs, etc.).
4. **S12** — `agent_trigger.py:42-45`: Reject `work_dir` with `..`, `~`, non-printable chars.
5. **M14** — `agent_chat.py:167-234`: `limit: int = Query(50, ge=1, le=500)`.
6. **M16** — `mcp_server.py:371-396`: Add agent-name collision check in `register_session` (mirroring `register_agent`).

### Backward-compat note

Removing `id` from Create schemas **may break clients that pass IDs intentionally** (the CLI may do this in some paths). Audit each caller before merging. If a client needs to specify an ID, use a separate `client_supplied_id: bool` flag and a `idempotency_keys` table.

---

## PR 6 — Hub auth, BOLA, perf

**Closes:** S3 (server half), M15, M17, T5
**File changes:** `hub/hub/auth.py`, `hub/hub/main.py`, `hub/hub/api/v1/agents.py`, `hub/hub/mcp_server.py`
**Test:** New `hub/tests/test_bola.py` (multi-tenant), enhance `hub/tests/test_auth.py`
**Risk:** High — touching the auth boundary
**Time:** 2-3 days

### Changes

1. **S3 (server)** — `auth.py:18, 26`: Remove `Query(None)` `token` fallback on all non-SSE endpoints. Add a separate `/api/v1/events/ticket` endpoint that returns a short-lived signed token; SSE clients must use this.
2. **M15** — `agents.py:96-377`: Rewrite `list_agents` to use `selectinload` / window functions, eliminate N+1.
3. **M17** — `mcp_server.py:244-264`: Remove the dead `agent` parameter from `update_task` or actually send it.
4. **T5** — New `hub/tests/test_bola.py`: Multi-tenant BOLA test that creates two projects with two API keys and tries to read project A's data with project B's key on every endpoint.
5. **Bonus** — `main.py`: Add `starlette` body-size middleware (default 1 MB) to prevent giant POSTs.

---

## PR 7 — DB & migrations

**Closes:** H5
**File changes:** `hub/hub/db/engine.py`, `hub/hub/main.py`, `hub/hub/migrations/versions/0007_…py`
**Test:** New `hub/tests/test_migrations.py` (round-trip every migration)
**Risk:** Low
**Time:** 1 day

### Changes

1. **H5** — `engine.py:39-86`, `main.py:21-26`: Run `alembic upgrade head` after `create_all` in `init_db` lifespan. Wrap in try/except so dev mode still works.
2. **DB-4** — `0007_…py`: Cap `error_summary` to `String(500)` instead of unbounded `Text`.

---

## PR 8 — Dead code & dedup

**Closes:** H7, Q4, Q5
**File changes:** `src/agentweave/cli.py`, `src/agentweave/watchdog.py`
**Test:** Existing tests must still pass
**Risk:** Low — pure deletion
**Time:** 0.5 day

### Changes

1. **H7** — `cli.py:1631-1749`, `watchdog.py:1830-1956`: Delete the 240 lines of dead `_build_agent_context` code. Have both callers import `context_builder.build_agent_context` directly.
2. **Q5** — `watchdog.py:3102-3132`: Delete the duplicate `_load_dotenv`; import from `utils.py`.

---

## PR 9 — Hub UI security

**Closes:** S3 (client half), S4, M19, M20, M22, M23 (client-side effects)
**File changes:** `hub/ui/src/hooks/useSSE.ts`, `hub/ui/src/store/configStore.ts`, `hub/ui/src/components/agents/ActivityLog.tsx`, `hub/ui/src/api/agentChat.ts`, `hub/ui/src/main.tsx`
**Test:** New `hub/ui/src/__tests__/` (vitest + jsdom) — currently no UI tests exist
**Risk:** Medium
**Time:** 2 days

### Changes

1. **S3 (client)** — `useSSE.ts:70`: Replace `?token=` with `fetch()` + `Authorization` header streamed via `ReadableStream`, OR (server-side) accept a short-lived signed ticket from `/events/ticket`.
2. **S4** — `configStore.ts:65, 71, 77`: Move `apiKey` to `sessionStorage`; persist only `theme` + `mode` to `localStorage`.
3. **M19** — `ActivityLog.tsx:75-81`: Fix the `paused` stale closure using the same ref pattern AGENTS.md documents.
4. **M20** — `agentChat.ts:22-23`: `sessionId !== NEW_SESSION_ID` (constant), not `!== 'new'`.
5. **M22** — `useSSE.ts:83-88, 100-103`: Clear `reconnectTimer` on `clearConfig`. Add reconnect cancellation on unmount.
6. **ErrorBoundary** — `main.tsx`: Add `<ErrorBoundary>` at the App root.

---

## PR 10 — Hub UI performance & dedup

**Closes:** M21, Q6, Q13, Q14, Q15
**File changes:** `hub/ui/src/api/agents.ts`, `hub/ui/src/components/...`, `hub/ui/src/App.tsx`
**Test:** Manual + Lighthouse
**Risk:** Low
**Time:** 2 days

### Changes

1. **M21** — `agents.ts:174-255`: Replace unconditional 2s poll with SSE-only. Reconciliation only on detected gap.
2. **Q6, Q13** — `hub/ui/src/lib/agentStatus.tsx` (new): Extract `contextBarColor`, `STATUS_CONFIG`, status-dot JSX, role-tag JSX.
3. **Q14** — `Sidebar.tsx:128-243`: Extract `<SidebarItem>`.
4. **Q15** — `App.tsx:44-53`: Mount only the active page, not all pages with CSS hidden.

---

## PR 11 — CLI/watchdog code quality

**Closes:** Q1, Q2, Q3, Q7, Q8
**File changes:** `src/agentweave/cli.py`, `src/agentweave/watchdog.py`, `src/agentweave/diagnostics.py`, `src/agentweave/utils.py`
**Test:** Existing tests should still pass
**Risk:** Low
**Time:** 2 days

### Changes

1. **Q1** — `cli.py`, `watchdog.py`: Replace ~100 `print()` calls with `logger.info(..., extra={"event": ...})`. Use existing `print_info/print_warning/print_error` helpers consistently.
2. **Q2** — `diagnostics.py`, `context_builder.py`: Standardize on `Optional[X]` (majority) — change `X | None` to `Optional[X]`.
3. **Q3** — `cli.py:171-549` (`cmd_init`, 379 lines): Split into `_init_session`, `_write_role_files`, `_write_root_contexts`, `_write_ai_context`, `_generate_skills`, `_write_yaml`. Each ≤ 50 lines.
4. **Q3** — `watchdog.py:2303-2707` (`_do_run_agent_subprocess`, 405 lines): Split per-runner.
5. **Q7** — `utils.py:66-68`: Stop truncating UUID4 — use full 32 chars or make length a parameter.

---

## PR 12 — Test coverage sweep

**Closes:** T1, T2, T3, T4, T5 (already), T6, T7, T8, T9, T10
**File changes:** New test files
**Test:** The tests themselves
**Risk:** Low
**Time:** 3-4 days

### New / enhanced test files

| New test file | Targets | Test count target |
|---|---|---|
| `tests/test_transport_git.py` | H1, H2, M11, M12, M13 | 20+ tests |
| `tests/test_eventlog.py` | M4, M6 | 5 tests |
| `tests/test_logging_handlers.py` | Logging handlers (no coverage today) | 8 tests |
| `tests/test_runner.py` | `get_agent_env`, `get_missing_api_key_var`, `build_claude_proxy_cmd` | 6 tests |
| `hub/tests/test_mcp_server.py` | All 20+ MCP tools | 30+ tests |
| `hub/tests/test_agent_chat.py` | Three-tier lookup (AGENTS.md devotes 60+ lines to a recent refactor; no regression test) | 10 tests |
| `hub/tests/test_jobs_crud.py` | Happy-path jobs CRUD, pause/resume/run/delete | 15 tests |
| `hub/tests/test_bola.py` | Multi-tenant isolation across every endpoint | 1 big test, ~50 lines |
| Enhance `tests/test_locking.py` | Two threads racing `acquire_lock` | 3 tests |
| Enhance `tests/test_http_transport.py` | HTTPError 401/404/500, malformed JSON, socket timeout, classification | 8 tests |

---

## Release prep (after PR 12)

1. Bump versions:
   - `hub/pyproject.toml`: 0.31.1 → 0.32.0
   - `src/agentweave/__init__.py`: 0.37.0 → 0.38.0
2. Update `CHANGELOG.md` with all 12 PR entries.
3. Update `ROADMAP.md` to mark Phase 13 (hosted Hub) as still planned.
4. Tag `v0.38.0` and `v0.32.0` (Hub).
5. Merge `audit/2026-q2-hardening` → `master`.
6. Push to PyPI (`twine upload` for `agentweave-ai`).
7. Publish GitHub release with notes.

---

## Risk reduction built in

- **Test-first** means every fix is provably correct before merge.
- **Each PR is independently shippable** — if you burn out at PR 6, you've already shipped the critical security and data-loss fixes.
- **Branch isolation** keeps `master` clean and gives you a single target to `git diff master` for the changelog.
- **Bump to v0.38.0-alpha.1** at PR 1 so anyone testing sees the audit work in progress.

## Dependencies

PR 2 (transport data-loss) and PR 5 (Hub input validation) are independent and can be done in parallel.
PR 9 (UI security) depends on PR 6 (Hub auth) — the server-side `/events/ticket` must exist before the client can use it.
PR 12 (test coverage) can run in parallel with everything else — many of the new tests are pre-requisites for the fixes (the audit calls this out explicitly).
