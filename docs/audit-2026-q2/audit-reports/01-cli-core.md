# Audit Report 01 — CLI Core

**Scope:** All Python files in `src/agentweave/`
**Date:** 2026-06-12
**Auditor:** opencode (MiniMax-M3) via Task tool, subagent_type=explore
**Method:** Read whole files, cross-reference with `tests/`, identify race conditions, error handling issues, dead code, security concerns, and architectural problems.

## Files in scope

```
src/agentweave/
├── cli.py
├── session.py
├── task.py
├── messaging.py
├── locking.py
├── validator.py
├── watchdog.py
├── eventlog.py
├── runner.py
├── roles.py
├── constants.py
├── utils.py
├── logging_config.py
├── context_builder.py
├── diagnostics.py
├── templates/
├── transport/
└── mcp/
```

---

## Critical bugs (data loss / crash / security)

### CLI-1. Locking TOCTOU + lost-lock race in `acquire_lock`

**File:** `src/agentweave/locking.py:35-56`

The "stale lock cleanup" path reads mtime, decides it's stale, then calls `lock_file.unlink()`. If two processes detect staleness simultaneously, both unlink, then both `open(x, "x")` succeed — one silently overwrites the other's lock. On Windows the second `unlink` may fail with `PermissionError`, leaving the next caller to wait the full 5-minute stale timeout.

**Fix:** Do the unlink + `open(x, "x")` in a single `os.open(O_CREAT|O_EXCL)` syscall, or use a Windows-friendly `msvcrt.locking()`.

### CLI-2. `is_locked` is read-only per AGENTS.md rule 6, but `acquire_lock` violates that contract

**File:** `src/agentweave/locking.py:100-127`

By deleting stale files inside a "read-time" function call, `acquire_lock` violates the documented contract. Worse, `is_locked` itself is not atomic — it reads file mtime, decides stale, returns False; a concurrent `acquire_lock` may then race the lock file.

**Fix:** Only do filesystem mutations in `acquire_lock`/`release_lock`; `is_locked` should be a pure `Path.exists()` check.

### CLI-3. Path-traversal vulnerability in `Message.load`

**File:** `src/agentweave/messaging.py:78-89`

No `message_id` regex validation. Compare to `task.py:107-108` and `jobs.py:224-226`, both of which validate IDs with `re.match(r"^[a-zA-Z0-9_-]+$", ...)`. The MCP server exposes `Message.load(message_id)` indirectly via `mark_read` (`mcp/server.py:119`) which a malicious Hub could call with IDs like `../../etc/passwd` to read arbitrary JSON.

**Fix:** Add the same regex check.

### CLI-4. 240 lines of dead code after `return` in `_build_agent_context`

**Files:** `src/agentweave/cli.py:1631-1749` and `src/agentweave/watchdog.py:1830-1956`

The function calls `context_builder.build_agent_context` and returns at line 1631, but lines 1633-1749 — the entire old hand-rolled version — are unreachable. A future maintainer will patch the wrong copy. Same pattern in `watchdog.py:1830` (dead body 1832-1956).

**Fix:** Delete the unreachable blocks (and unify the two near-identical wrapper functions — `cli._build_agent_context(agent, session, version)` and `watchdog._build_agent_context(agent, session)` differ only in the version comment arg).

### CLI-5. File-handle leak in `cmd_start`

**File:** `src/agentweave/cli.py:1869-1870`

`log_fh = open(WATCHDOG_LOG_FILE, "a", encoding="utf-8")` is passed to `Popen(stdout=log_fh, stderr=log_fh, ...)`. The handle is never closed in the parent process (the comment `# noqa: SIM115` actively suppresses the lint check). On Windows, multiple `cmd_start` calls in the same Python process accumulate open handles; the file may stay locked.

**Fix:** Open with `with open(...)` and pass via `_sp.Popen` before exiting the `with`, or pass a file path and reopen it in the child.

---

## Likely bugs (subtle, may not have manifested)

### CLI-6. `Task.move_to_completed` is not atomic

**File:** `src/agentweave/task.py:172-181`

Writes completed file first, then unlinks active. A crash between the two leaves the task in both directories, and `Task.list_all(active_only=False)` returns it twice. The codebase never uses `os.replace`/`os.rename` for atomic on-disk swap.

**Fix:** `os.replace(active_path, completed_path)` after writing to a sibling temp file.

### CLI-7. `cmd_quick` validates before acquiring the lock

**File:** `src/agentweave/cli.py:1101-1185`

`Task.create()` → `validate_task()` → `acquire_lock(f"task_{task.id}")`. If two users race a quick delegation, both pass validation and both try to lock the same `task_{id}` (UUID4 collision is negligible, so this is academic), but the message creation at lines 1157-1164 and the transport.send_task at line 1147 happen **inside** the lock — only the bare `Task.create` is unprotected. Acceptable but inconsistent with `cmd_task_update` which locks first.

### CLI-8. `cmd_msg_send` has no lock at all

**File:** `src/agentweave/cli.py:1335-1365`

Two concurrent invocations would not corrupt state (UUIDs are unique), but the diagnostic log on line 174-185 may interleave badly and the recipient could see two near-simultaneous messages with confusing ordering. Not a correctness bug, just untidy.

### CLI-9. `Message.mark_read` reads `self._data` then writes twice

**File:** `src/agentweave/messaging.py:99-119`

Between archive and unlink, the message exists in both directories; `get_inbox` filters on `to == agent` so it's not duplicated in the user's view, but `get_outbox` (lines 196-212) returns it from both. Minor.

### CLI-10. `run_proc.wait()` does not handle SIGTERM cleanly

**File:** `src/agentweave/watchdog.py:1631`

If the watchdog receives Ctrl-C during `proc.wait()`, the partial stdout loop in `_drain_stderr` may not have flushed all error context. The `redact_secrets` in line 2688 then logs an empty `stderr_tail`. Mostly cosmetic.

### CLI-11. `_load_triggered_ids` race

**File:** `src/agentweave/watchdog.py:1959-1989`

Reads the JSON file, prunes old entries, then re-writes the file. Two watchdogs starting at the same time will both read the same set, then the second's write will discard the first's fresh additions. The seen-set survives only as a 24-hour dedup hint, so worst case is one duplicate Hub trigger. Not catastrophic.

### CLI-12. Heartbeat age uses naive `datetime.now()`

**File:** `src/agentweave/eventlog.py:37-38`

`datetime.fromisoformat(ts)` may return a naive or aware datetime depending on the writer; `cli.py:944` writes with `datetime.now().isoformat()` (naive), but `eventlog.py:27` writes with `datetime.now().isoformat(timespec="seconds")` (also naive), and the watchdog writes with `datetime.now(timezone.utc)` (aware). Subtracting aware from naive raises `TypeError`. The `except Exception: return None` on line 39 silently masks this — operators see "DEAD" status without explanation.

**Fix:** Standardize on `datetime.now(timezone.utc).isoformat()` everywhere.

### CLI-13. `Popen(..., text=True)` without `encoding="utf-8"`

**File:** `src/agentweave/watchdog.py:2480-2489`

Stderr is decoded with the system locale (cp1252 on Western Windows). A Kimi error containing non-ASCII crashes `for raw in proc.stderr` with `UnicodeDecodeError` mid-thread, swallowing the rest of the stderr. The Hub logging on line 2418-2428 then misses later errors.

**Fix:** Pass `encoding="utf-8", errors="replace"`.

### CLI-14. `subprocess.run` for `claude` with no `timeout`

**File:** `src/agentweave/cli.py:4122`

Can never time out by design, so a stuck Claude session freezes the user's terminal until they Ctrl-C. Same issue at `cli.py:2405` for `docker compose version` and `cli.py:2312-2322` for `git` subprocess calls.

**Fix:** Add `timeout=10` for version checks, `timeout=1800` (30min) for `claude`.

### CLI-15. `recent_stderr` is mutated from a daemon thread

**File:** `src/agentweave/watchdog.py:2394-2440`

A `del recent_stderr[:-10]` while another thread does `recent_stderr.append(...)` is a CPython implementation detail (GIL keeps the list header atomic) but a `RuntimeError: list changed size during iteration` can still surface. Low likelihood but the fix is `collections.deque(maxlen=10)` plus a `threading.Lock`.

### CLI-16. `generate_id` truncates UUID4 to 8 hex chars

**File:** `src/agentweave/utils.py:66-68`

32 bits, so collision probability hits 1% around 65k IDs. Tests in `test_utils.py:18-20` only check 50. The CLAUDE.md "zero runtime dependencies, simple" philosophy is fine, but the failure mode is silent overwrite.

### CLI-17. `cmd_inbox` does not mark messages read

**File:** `src/agentweave/cli.py:1368-1402`

In contrast to MCP's `get_inbox` in `mcp/server.py:102-106` which auto-archives. Same `MessageBus.get_inbox(agent)` call, but the user has to follow up with `agentweave msg read <id>` for every message. Inconsistent UX between CLI and MCP.

### CLI-18. `heartbeat` does two round-trips per call

**File:** `src/agentweave/mcp/server.py:1075-1115`

`is_agent_registered` then the actual POST. Trivial perf issue.

### CLI-19. `_req.urlretrieve` has no integrity check

**File:** `src/agentweave/cli.py:2549, 2558`

Downloads `docker-compose.yml` and `.env` from GitHub raw with no checksum, no signature. MITM risk is low (TLS) but worth noting for a "zero-deps" framework.

### CLI-20. `shell=True` in `cmd_mcp_setup`

**File:** `src/agentweave/cli.py:1869 + cli.py:2031`

The shell=True path is used for Windows `.cmd` resolution. The command arguments are all built from `RUNNER_CONFIGS["mcp_add_cmd"]` (hardcoded) and `server_cmd = "agentweave-mcp"` (hardcoded), so no user input flows in — but the principle is still risky.

**Fix:** Prefer `subprocess.Popen(cmd, creationflags=DETACHED_PROCESS)` for the `.cmd` shim.

---

## Code quality issues

### CLI-Q1. `print()` in command code, not `logging`

**Files:** `src/agentweave/cli.py`, `src/agentweave/watchdog.py`

Roughly 100 `print(...)` calls in `cli.py` and 30+ in `watchdog.py`. Per AGENTS.md "logging architecture", structured `logger.info(..., extra={"event": "..."})` should be used in production code; `print()` is only appropriate for user-facing CLI banners.

### CLI-Q2. `_generate_claude_skills` and `_generate_codex_skills` are near-duplicates

**File:** `src/agentweave/cli.py:556-640, 598-640`

Same loop body, same substitutions, same `count` increment. Could be unified with a `codex: bool = False` arg.

### CLI-Q3. `_KimiParser` and `_KimiWireParser` share state machine logic

**File:** `src/agentweave/watchdog.py:875-1027, 1042-1216`

The Python-repr and JSON-RPC formats are different, but the rendering could share a `RenderContext` helper. ≈350 lines of parser code is hard to test in isolation.

### CLI-Q4. Functions over 50 lines (AGENTS.md rule)

- `cli.py:171-549` `cmd_init` is 379 lines. Split into `_init_session`, `_write_role_files`, `_write_root_contexts`, `_write_ai_context`, `_generate_skills`, `_write_yaml`.
- `cli.py:1613-1749` `_build_agent_context` (137 lines, plus 120 of dead code). Already flagged.
- `cli.py:1752-1806` `_kill_stale_watchdogs` is 55 lines.
- `cli.py:2494-2601` `cmd_hub_start` is 108 lines.
- `watchdog.py:2303-2707` `_do_run_agent_subprocess` is 405 lines. This is the worst — it owns subprocess IO, Kimi wire parsing, Codex JSONL parsing, stderr draining, session-id tracking, context-usage writes, retry-on-stale. Should be split per-runner.
- `mcp/server.py:1129` `main` is one line but the file is 1129 lines of decorators.

### CLI-Q5. `datetime.utcnow()` is deprecated in Python 3.12+

**Files:** `src/agentweave/cli.py:3514-3515`, `src/agentweave/watchdog.py:495`, `src/agentweave/mcp/server.py:386-387, 773`

Emits `DeprecationWarning`. Returns naive datetimes that mix badly with the rest of the codebase (which uses `datetime.now(timezone.utc)`).

**Fix:** Switch to `datetime.now(timezone.utc)`.

### CLI-Q6. Mixed type hint style

**Files:** various

`Optional[X]` dominates but `X | None` (PEP 604) appears in `diagnostics.py:54-55`, `context_builder.py:65, 116, 450, 451`. Pick one.

### CLI-Q7. Inconsistent `except Exception` patterns

~90 `except Exception:` or `except Exception as e:` across the codebase. Many swallow errors silently (`eventlog.py:39`, `session.py:385`, `cli.py:1599-1600`, `watchdog.py:1597`, `transport/http.py:466`, `mcp/server.py:763-784`, etc.).

**Fix:** Define `CLIError`, `HubError`, `TransportError` and let catchers decide whether to swallow.

### CLI-Q8. `try/except: pass` patterns that swallow real errors

Twenty-plus places. The user specifically called these out. Highest-impact:
- `cli.py:181-183` (init migration swallows ALL exceptions while reading `session.json`)
- `cli.py:1607-1608` (`_get_project_instructions` swallows OSError)
- `cli.py:1746-1747` (silent ai_context.md read fail in dead code)
- `eventlog.py:39` (silent heartbeat parse fail masks the timezone bug above)

### CLI-Q9. Inconsistent banner formatting

**File:** `src/agentweave/cli.py`

`[OK]`, `[WARN]`, `[ERR]`, `[INFO]`, `[STAT]`, `[AGENTS]`, `[WATCH]`, `[TASKS]`, `[REVIEW]`, `[MSG]`, `[DOCTOR]`, `[PING]`, `[JOB]`, `[TRIGGER]`, `[STOP]`, `[HUB]`, `[JOB]`, `[SESSION]`, `[FILES]`, `[CONFIG]`, `[DIR]`, `[SKILLS]`, `[SKIP]`, `[CTX]`, `[WATCH]`, `[PILOT]`. 25+ tag styles. The `print_info/print_warning/print_success/print_error` helpers exist in `utils.py` but most command code doesn't use them.

---

## Security concerns

### CLI-S1. API key handling is correct (per spec)

`cmd_switch` (cli.py:3968-4029) prints `export {key}={value}` for `eval` consumption — values come from `os.environ.get(api_key_var, "")`, never stored. The user's system reminder claim ("never stored, only env var names") is verified: `runner.py:16-38` `get_agent_env` reads from `os.environ` and returns a transient dict; nothing is written to disk except in `transport.json` (api_key field, gitignored per AGENTS.md).

### CLI-S2. `transport.json` stores `api_key` in plain text

**File:** `src/agentweave/cli.py:2261`

AGENTS.md says it's gitignored and may contain secrets — this is correct, but the file **must not** be world-readable on multi-user Unix systems. No `chmod 600` is performed.

**File:** `src/agentweave/cli.py:2874-2876`

`save_json(TRANSPORT_CONFIG_FILE, ...)` writes the api_key. If `TRANSPORT_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)` creates a new directory on a shared host, permissions default to umask. Risk: low for solo devs, medium on shared hosts.

### CLI-S3. Path traversal in `Message.load`

Already flagged as CLI-3.

### CLI-S4. `load_dotenv` doesn't enforce UTF-8 BOM

**File:** `src/agentweave/utils.py:21-45`

The `if " #" in value` test on line 38 is a string match that may falsely split values containing `" #"`. Minor, only affects hand-edited `.env` files.

### CLI-S5. `Request(f"{url}/api/v1/agents/register", data=body, ...)`

**File:** `src/agentweave/mcp/server.py:898`

`body` includes `name`, `spawn_cmd`, etc. that an agent self-registers. `spawn_cmd` is a list passed to the Hub; the Hub presumably validates, but if the Hub has any path-traversal in its handling of `spawn_cmd` (e.g. logging it unsanitized), the agent could inject control chars.

### CLI-S6. `cmd_mcp_setup` uses `shell=_shell` (= True on Windows)

**File:** `src/agentweave/cli.py:2025-2132`

Already flagged as CLI-20.

### CLI-S7. `except Exception: pass` in the log-follow loop

**File:** `src/agentweave/cli.py:1963-1965`

Masks ALL errors during log streaming. An attacker who can write to `events.jsonl` could cause a JSON parse error to silently disable the log viewer.

### CLI-S8. `urlretrieve` for compose/env files

**File:** `src/agentweave/cli.py:2549, 2558`

Already flagged as CLI-19.

### CLI-S9. `HubHandler.emit` swallows all exceptions

**File:** `src/agentweave/logging_handlers.py:65-81`

Intentional (logging must never crash), but it means a misconfigured Hub URL silently disables all Hub log forwarding. No `logger.debug` of the failure either.

---

## Test gaps

| Source file | Test file | Coverage |
|---|---|---|
| `src/agentweave/eventlog.py` | **none** | none |
| `src/agentweave/logging_handlers.py` | **none** | none |
| `src/agentweave/runner.py` | **none** | none |
| `src/agentweave/transport/git.py` | **none** | none |
| `src/agentweave/templates/__init__.py` | **none** (test_skill_templates.py tests something else) | none |
| `src/agentweave/cli.py` (4999 lines) | `test_cli.py` (231 lines), `test_init.py`, `test_activate.py`, `test_hub_commands.py`, `test_cli_pilot.py` | partial |
| `session.py:sync_agents` | partial via `test_session.py:123-168` | partial |
| `_load_agent_session`, `_save_agent_session` in watchdog.py | none | none |
| `_kill_stale_watchdogs` in cli.py | none | none |

### Test spot checks

- **`test_watchdog.py:586-610` `test_known_model_limit`**: correct. The math (`int(146000/272000*100) = 53`) matches. Good test.
- **`test_watchdog.py:611-634` `test_unknown_model_fallback`**: correct. Asserts 57% for unknown model. Good test.
- **`test_watchdog.py:262-286` `test_codex_yolo_adds_bypass_flag`**: passes, but the inner assertion `assert "--full-auto" not in cmd` (line 286) only fires when yolo=True. The outer assertion (line 266) for the non-yolo case checks `not in cmd` and `in cmd` — these are the two correct opposite ends. Good test.
- **`test_locking.py:41-46` `test_double_acquire_blocks`**: correct in isolation, but does not catch the stale-lock race described in CLI-1. The test only checks the happy path of "second acquire times out".
- **`test_session.py:160-168` `test_session_sync_agents_clears_model_when_removed`**: passes a `None` model and asserts it's cleared. The actual code path in `session.py:298-300` does `del agent_data["model"]`. Test is correct, but the helper passes `None` as the literal value, not as a missing key.
- **`test_init.py`**: comprehensive. Skimmed all 14 tests, all look sound.
- **`test_activate.py`**: comprehensive. Skimmed all 9 tests, all look sound.
- **`test_http_transport.py`**: uses a manually-constructed context manager mock that won't actually behave like `urllib.urlopen` for retry/redirect handling. Tests work but only because the SUT is one-shot.

---

## Architectural improvements

### CLI-A1. Duplicate code: `_build_agent_context`

`cli.py:1613-1749` and `watchdog.py:1809-1956` are near-duplicates of each other and of `context_builder.build_agent_context`. Three implementations of the same logic. Already flagged as CLI-4.

### CLI-A2. Duplicate code: `_load_dotenv`

`utils.py:21-45` and `watchdog.py:3102-3132` have nearly identical implementations. The watchdog copy adds no value. Delete one and import the other.

### CLI-A3. Circular import risk

`cli.py` and `watchdog.py` both import each other. `mcp/server.py:788` does `from ..cli import _build_agent_context` — `cli` imports `mcp` indirectly via the `mcp` extra? `watchdog.py:1819` does `from .cli import _get_project_instructions` — but `cli.py` doesn't import `watchdog`. So no cycle today, but the coupling is fragile. Move `_get_project_instructions` to `utils.py` or a new `project.py`.

### CLI-A4. Public API surface

`__init__.py` exports `main, Session, Task, TaskStatus, Message, MessageBus, get_agent_roles, add_role_to_agent, remove_role_from_agent, set_agent_roles, get_available_roles`. The `TaskStatus` is exported but the enum has no public consumer inside the package (most code uses string literals like `"in_progress"` directly). Either add consumers or remove from the public API.

### CLI-A5. Inconsistent error types

`LockError` (locking.py) and `ValidationError` (validator.py) exist as named exceptions. But the rest of the package uses raw `Exception`, `RuntimeError`, or `bool` returns. Consider a unified `AgentWeaveError` hierarchy: `ValidationError`, `LockError`, `TransportError`, `ConfigError`, `CLIError`.

### CLI-A6. MCP server vs CLI shared logic

`mcp/server.py` reimplements file IO, Hub HTTP calls, and role lookups that exist in `cli.py` and `watchdog.py`. Consider a thin `client.py` for Hub interactions shared by cli/watchdog/mcp.

### CLI-A7. Logging handlers recursion guard

`logging_handlers.py` `HubHandler.emit` calls `t.push_log()` which may itself fail. The recursion guard mentioned in the docstring is not enforced — `push_log` is not decorated, so if anyone ever adds a `logger.info(...)` call inside `HttpTransport.push_log`, infinite recursion results.

**Fix:** Add `if record.name == "agentweave.transport.http": return` as a hard guard at the top of `emit`.

---

## Quick wins (easy fixes with high signal)

1. **`locking.py:35-56`** — Replace open-read-unlink with `os.open(path, O_CREAT|O_EXCL|O_WRONLY)`. Eliminates the entire TOCTOU window in 5 lines.
2. **`messaging.py:78-89`** — Add `re.match(r"^[a-zA-Z0-9_-]+$", message_id)` check. Closes the path-traversal vector.
3. **`cli.py:3514-3515, watchdog.py:495, mcp/server.py:386-387, 773`** — Replace `datetime.utcnow()` with `datetime.now(timezone.utc)`. Four replacements, no more `DeprecationWarning` on 3.12+.
4. **`cli.py:1631-1749, watchdog.py:1830-1956`** — Delete the 240 lines of dead code. Have one caller delegate to the other (or both delegate to `context_builder`).
5. **`cli.py:2405, 2312-2322, 4122`** — Add `timeout=10` to `subprocess.run` calls. Prevents indefinite hangs.
6. **`eventlog.py:27, cli.py:944, mcp/server.py:773`** — Switch naive `datetime.now().isoformat()` to `datetime.now(timezone.utc).isoformat()`.
7. **`diagnostics.py:53-56`** — Standardize on `Optional[str]`.
8. **`utils.py:66-68`** — Switch `generate_id` to use full UUID4 (no truncation).
9. **`cli.py:4122`** — `subprocess.run` for `claude` should at minimum take a 30-minute timeout and surface a clear error.
10. **`logging_handlers.py:65-81`** — Add recursion guard at top of `emit`.

---

## Summary

| Severity | Count |
|---|---|
| Critical (data loss / crash / security) | 5 |
| Likely (subtle / untested path) | 14 |
| Code quality | 9 |
| Security | 9 |
| Test gaps | 9 files |
| Architectural | 7 |
| Quick wins | 10 |

The single most important fix is the locking TOCTOU (CLI-1) + the path-traversal in `Message.load` (CLI-3) — both are concrete exploitable bugs. The dead-code blocks (CLI-4) are the highest-priority cleanup because they're actively misleading future maintainers.
