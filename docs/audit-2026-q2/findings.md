# Consolidated Findings — Prioritized Bug List

All 60 issues found in the 2026 Q2 audit, deduped across the 4 explore-agent reports and grouped by severity. Each entry has a file:line reference and a one-line fix hint.

For the raw agent output that produced this list, see `audit-reports/`.

For the PR-by-PR execution plan that closes these, see `pr-roadmap.md`.

---

## CRITICAL (1)

| # | Issue | File:line |
|---|---|---|
| **C1** | **SPA fallback leaks the live API key to any unauthenticated request.** `serve_spa` catch-all injects `aw_live_…` into the HTML response body. `curl http://hub:8000/anything` returns a working key. | `hub/hub/main.py:66-99` |

**Fix:** Stop injecting the key. Have the SPA call `/api/v1/setup/token` (already localhost-only) on first load. See `pr1-spa-key-leak.md` for the full test-first plan.

---

## HIGH — Data loss / silent corruption (8)

| # | Issue | File:line |
|---|---|---|
| **H1** | **GitTransport `ls-tree` race wipes the entire orphan branch.** If `ls-tree` fails for any reason after `ls-remote` succeeded, the code falls through to a "new branch" path and pushes a single-file commit. All other messages on the branch are permanently lost. | `src/agentweave/transport/git.py:130-139` |
| **H2** | **GitTransport `send_message` silently drops the message after 3 push failures.** No local outbox, no buffer, no recovery. User retypes. | `src/agentweave/transport/git.py:166-176` |
| **H3** | **HttpTransport no retry on 5xx / 429 / transient errors.** Every blip = lost message. | `src/agentweave/transport/http.py` (missing logic) |
| **H4** | **Locking TOCTOU race in `acquire_lock`.** Stale-lock cleanup + `open(x, "x")` is racy; on Windows a `PermissionError` leaves the next caller waiting the full 5-minute timeout. | `src/agentweave/locking.py:35-56` |
| **H5** | **Alembic migrations are never auto-run at startup.** `init_db` only calls `create_all`. If you upgrade and a new column is needed, the write fails with `OperationalError: no such column` on the first job failure. | `hub/hub/db/engine.py:39-86`, `hub/hub/main.py:21-26` |
| **H6** | **HTTP transport `_request` doesn't catch `json.JSONDecodeError`.** A 200 with HTML body (reverse proxy error page, captive portal) crashes the agent. | `src/agentweave/transport/http.py:97-100` |
| **H7** | **240 lines of dead code** in `_build_agent_context` (cli + watchdog). Future maintainers will patch the wrong copy. | `src/agentweave/cli.py:1631-1749`, `src/agentweave/watchdog.py:1830-1956` |
| **H8** | **File-handle leak in `cmd_start`.** `# noqa: SIM115` suppresses the lint check. Multiple `cmd_start` calls accumulate open handles. | `src/agentweave/cli.py:1869-1870` |

---

## HIGH — Security (12)

| # | Issue | File:line |
|---|---|---|
| **S1** | **Path traversal in `_load_role_content`.** Accepts arbitrary `role` string. `?role=../../etc/passwd` reads any file. | `hub/hub/api/v1/agents.py:495-533, 875-890` |
| **S2** | **Path traversal in `Message.load`.** No `message_id` regex (compare to `task.py:107` which validates). MCP `mark_read` is the surface. | `src/agentweave/messaging.py:78-89` |
| **S3** | **API key in SSE URL** — visible in nginx access logs, browser history, referer headers. (Compounded by `auth.py` accepting `?token=` on every endpoint.) | `hub/ui/src/hooks/useSSE.ts:70`, `hub/hub/auth.py:18,26` |
| **S4** | **API key in `localStorage`.** Any XSS exfiltrates the live key. Should be `sessionStorage` at most. | `hub/ui/src/store/configStore.ts:65, 71, 77` |
| **S5** | **Mass assignment.** `MessageCreate`, `TaskCreate`, `JobCreate` all let clients pick `id` / `timestamp` / `created_at`. | `hub/hub/schemas/messages.py:19-21`, `schemas/tasks.py:33-34`, `schemas/jobs.py:17` |
| **S6** | **No input length limits anywhere.** Multi-GB POSTs into `content`/`message`/etc., then broadcast verbatim to every SSE subscriber (N× amplification). | All `hub/hub/schemas/*.py` |
| **S7** | **`HubTransportError` includes full response body in the error message.** A Hub error page that echoes the request URL will write the API key (which travels in `?token=…`) to `events.jsonl`. | `src/agentweave/transport/http.py:111-113` |
| **S8** | **`transport.json` written with world-readable default umask** on multi-user Unix. | `src/agentweave/cli.py:2195, 2256, 2874-2876` |
| **S9** | **`urlretrieve` for compose/.env with no integrity check.** | `src/agentweave/cli.py:2549, 2558` |
| **S10** | **No response body size cap on HttpTransport.** Multi-GB Hub response = OOM the agent. | `src/agentweave/transport/http.py` |
| **S11** | **No file permissions hardening on message files** (default 0644). Sensitive content world-readable. | `src/agentweave/transport/local.py` |
| **S12** | **No `subprocess` timeout on `claude` invocation.** Can never time out, freezes the user's terminal. | `src/agentweave/cli.py:4122` |

---

## MEDIUM — Bugs (23)

| # | Issue | File:line |
|---|---|---|
| **M1** | N+1 in MCP `get_inbox` — 1 GET + N PATCH round-trips. 100 messages = 101 round-trips, blocking the event loop. | `hub/hub/mcp_server.py:121-143` |
| **M2** | All MCP tools are sync `def`, not `async def` — blocking I/O on the event loop for 20+ tools. | `hub/hub/mcp_server.py` (entire file) |
| **M3** | `datetime.utcnow()` deprecated in Python 3.12+. Emits `DeprecationWarning`, returns naive datetime that mixes badly with aware datetimes. | `cli.py:3514-3515`, `watchdog.py:495`, `mcp/server.py:386-387, 773` |
| **M4** | Timezone bug in `get_heartbeat_age` — mixes aware/naive datetimes, silently masked by `except Exception: return None`. The "DEAD" status indicator disappears. | `src/agentweave/eventlog.py:27-39` |
| **M5** | `Popen(..., text=True)` without `encoding="utf-8"` — Kimi errors with non-ASCII crash `proc.stderr` mid-thread on Windows (cp1252). | `src/agentweave/watchdog.py:2480-2489` |
| **M6** | `get_heartbeat_age` timezone crash is silently swallowed → user sees "DEAD" without explanation. | `src/agentweave/eventlog.py:37-39` |
| **M7** | No retry on git `subprocess.run` — `git fetch` hang kills the watchdog. | `src/agentweave/transport/git.py:55-65, 92-95` |
| **M8** | `archive_message` is read-modify-delete with no locking (LocalTransport) — message can exist in both pending and archive directories. | `src/agentweave/transport/local.py:38-53` |
| **M9** | `Message.mark_read` has the same pending-archive race as `archive_message`. | `src/agentweave/messaging.py:99-119` |
| **M10** | `Task.move_to_completed` writes-then-unlinks (not atomic) — crash between leaves duplicate. | `src/agentweave/task.py:172-181` |
| **M11** | Git transport `_save_seen_set` race — two agents on the same machine can lose updates; messages re-delivered forever. | `src/agentweave/transport/git.py:182-192, 300-302` |
| **M12** | Git transport status-update file parsing is fragile — regex `^(.+?)-\d{4}` misparses task_ids that contain digit-4-prefixed substrings (e.g. UUIDs starting with `4b8a…`). | `src/agentweave/transport/git.py:340-352` |
| **M13** | Git transport `_iso_compact` is second-precision, not millisecond (despite docstring) — same-second bursts have ~1-in-50k collision chance per pair. | `src/agentweave/transport/git.py:50-52` |
| **M14** | `agent_chat.get_recent_chat` `limit` parameter has no bounds — `?limit=999999999` returns everything. | `hub/hub/api/v1/agent_chat.py:167-234` |
| **M15** | `list_agents` N+1 query — 4 queries per agent, no caching, no pagination. | `hub/hub/api/v1/agents.py:96-377` |
| **M16** | `register_session` doesn't check agent-name collision — a misbehaving agent can hijack the principal's identity. | `hub/hub/mcp_server.py:371-396` |
| **M17** | `update_task` in MCP has dead `agent` parameter — declared, documented, never sent. | `hub/hub/mcp_server.py:244-264` |
| **M18** | `agentweave get_inbox` (CLI) doesn't auto-mark messages read — inconsistent with MCP `get_inbox` which does. | `src/agentweave/cli.py:1368-1402` |
| **M19** | `ActivityLog.tsx` `paused` stale closure — same pattern AGENTS.md documents as already fixed elsewhere. Pause button does nothing. | `hub/ui/src/components/agents/ActivityLog.tsx:75-81` |
| **M20** | `agentChat.ts:22` `sessionId !== 'new'` — should be `NEW_SESSION_ID = '__new__'`. Currently fires for the "new chat" branch. | `hub/ui/src/api/agentChat.ts:22-23` |
| **M21** | `useAgentOutput` triple-polls per agent per page (poll + SSE + React Query, three subscribers per page). | `hub/ui/src/api/agents.ts:174-255` |
| **M22** | `useSSE` `reconnectTimer` not cleared on `clearConfig` — stale reconnect after the user logs out. | `hub/ui/src/hooks/useSSE.ts:83-88, 100-103` |
| **M23** | `urllib.request.urlopen` default timeout is unlimited in `mcp_server._hub_request`. | `hub/hub/mcp_server.py:70` |

---

## MEDIUM — Test gaps (10)

| # | Gap | Risk |
|---|---|---|
| **T1** | `tests/test_git_transport.py` does not exist. The riskiest component has zero coverage. | Critical |
| **T2** | `tests/test_locking.py` has no concurrent test — only sequential. | High |
| **T3** | `hub/hub/mcp_server.py` has zero tests — 20+ MCP tools. | High |
| **T4** | `hub/hub/api/v1/agent_chat.py` has zero direct tests — AGENTS.md devotes 60+ lines to a recent refactor; no regression test. | High |
| **T5** | No multi-tenant BOLA test — every endpoint with `project_id` filter is uncovered. | High |
| **T6** | `hub/hub/api/v1/jobs.py` happy-path CRUD untested. | Medium |
| **T7** | No tests for `agent_trigger.py` `[Session:]` / `[NewSession]` tag generation. | Medium |
| **T8** | `tests/test_http_transport.py` doesn't test HTTPError 401/404/500, malformed JSON, socket timeout, or `HubTransportError.classification`. | Medium |
| **T9** | `eventlog.py`, `logging_handlers.py`, `runner.py` have no test files. | Medium |
| **T10** | `tests/test_setup.py:18-34` is a meta-test using `inspect.getsource()` instead of a real HTTP request. | Low |

---

## LOW — Code quality (16)

| # | Issue | File:line |
|---|---|---|
| **Q1** | ~100 `print()` calls in `cli.py` / `watchdog.py` should be `logger` with structured `extra={"event": ...}`. | `cli.py`, `watchdog.py` (many lines) |
| **Q2** | Mixed `Optional[X]` / `X \| None` — pick one. | `diagnostics.py`, `context_builder.py` (PEP 604) vs. rest (Optional) |
| **Q3** | `cmd_init` is 379 lines (limit 50). `_do_run_agent_subprocess` is 405 lines. | `cli.py:171-549`, `watchdog.py:2303-2707` |
| **Q4** | Duplicate `_build_agent_context` in `cli.py` and `watchdog.py` (now dead — see H7). | `cli.py:1613-1749`, `watchdog.py:1809-1956` |
| **Q5** | Duplicate `_load_dotenv` in `utils.py` and `watchdog.py`. | `utils.py:21-45`, `watchdog.py:3102-3132` |
| **Q6** | `contextBarColor` / `STATUS_CONFIG` / status-dot JSX duplicated 3-5 times across UI components. | `hub/ui/src/components/agents/AgentCard.tsx`, `AgentsPage.tsx`, `AgentDetailPanel.tsx`, `OverviewPage.tsx` |
| **Q7** | `generate_id` truncates UUID4 to 8 hex chars (32 bits, ~1% collision at 65k). | `src/agentweave/utils.py:66-68` |
| **Q8** | ~20 `try/except: pass` patterns that swallow real errors. Highest impact: `eventlog.py:39` (masks the timezone crash M4/M6), `cli.py:181-183` (init migration), `cli.py:1607-1608` (project instructions). | various |
| **Q9** | `urllib` redirect handler doesn't re-send `Authorization` on cross-host redirect. | `http.py` (default urllib behavior) |
| **Q10** | Inconsistent banner formatting: `[OK]`, `[WARN]`, `[ERR]`, `[INFO]`, `[STAT]`, `[AGENTS]`, etc. — 25+ tag styles. | `cli.py` print calls |
| **Q11** | `git` transport has no `User-Agent` header on HTTP requests. | `src/agentweave/transport/http.py:97-100` |
| **Q12** | Module-level state in `useSSE.ts` (`listeners`, `eventSource`, `eventBuffer`) — makes unit testing impossible. | `hub/ui/src/hooks/useSSE.ts:30-32` |
| **Q13** | `MagicBarColor` function reimplemented 3-4 times. | UI components |
| **Q14** | "Nav item button" JSX duplicated 3 times in `Sidebar.tsx`. | `hub/ui/src/components/layout/Sidebar.tsx:128-243` |
| **Q15** | All pages mounted concurrently with CSS hidden, so all `useEffect`s and `setInterval`s run. | `hub/ui/src/App.tsx:44-53` |
| **Q16** | `date-fns/format` vs `toLocaleDateString` vs `toLocaleTimeString` mixed across components. | various UI |

---

## Severity distribution summary

| Severity | Count | Status |
|---|---|---|
| CRITICAL | 1 | PR 1 |
| HIGH data-loss | 8 | PRs 2, 7, 8 |
| HIGH security | 12 | PRs 3, 4, 5, 6, 9 |
| MEDIUM bugs | 23 | PRs 2, 3, 4, 5, 6, 7, 9, 10 |
| MEDIUM test gaps | 10 | PR 12 |
| LOW quality | 16 | PRs 8, 10, 11 |

**Total:** 60 issues → 12 PRs. Average 5 issues per PR. Largest is PR 2 (transport data-loss, ~10 issues). Smallest is PR 1 (one issue, but it's the CRITICAL one).
