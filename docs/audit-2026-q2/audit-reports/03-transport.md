# Audit Report 03 — Transport Layer

**Scope:** `src/agentweave/transport/`
**Date:** 2026-06-12
**Auditor:** opencode (MiniMax-M3) via Task tool, subagent_type=explore
**Method:** Read whole files, focus on race conditions, atomic file ops, error handling, network resilience.

## Files in scope

```
src/agentweave/transport/
├── base.py      (BaseTransport ABC)
├── local.py     (LocalTransport — filesystem)
├── git.py       (GitTransport — git orphan branch)
├── http.py      (HttpTransport — stdlib urllib to Hub REST)
└── config.py    (factory that reads transport.json)
```

## Background

The transport layer is the core of AgentWeave. It handles:
- Sending inter-agent messages
- Sending tasks
- Reading inboxes
- Archiving messages
- Pulling on transport changes (git pull, HTTP poll)

Three implementations: local FS, git orphan branch, HTTP to Hub. The transport must be **safe under concurrent access from multiple agents on the same machine** and **resilient to network failures** (for HTTP).

---

## Critical bugs (data corruption / loss / hang)

### T-CRIT-1. `branch_exists` and `ls-tree` race condition → CATASTROPHIC data loss

**File:** `src/agentweave/transport/git.py:130-139`

At line 130 `branch_exists_on_remote()` says the branch exists. At line 134 `ls-tree <remote_ref>` is called. If `ls-tree` fails (rc != 0) — for any reason: slow fetch, branch just deleted on remote by another actor, corrupt local ref, transient network blip — the resulting `tree_entries` is empty string (the `_run_git` helper returns `""` for `out` on `rc != 0`). The code then **silently** builds `mktree_input` containing **only the new file** and pushes a new commit whose parent is the new (single-file) tree. Result: **the entire orphan branch is replaced by a tree containing only the message you just sent — every other message on the branch is permanently lost from the remote.**

**Trigger conditions (all realistic):**
1. First push from a fresh machine: `git fetch` is slow, `ls-remote` returns the branch, but `origin/<branch>` ref isn't materialized yet → `ls-tree` fails → push wipes the branch.
2. A CI script force-deletes orphan branches on the remote between the two checks.
3. User A and User B both push simultaneously; one of them happens to read a partially-orphaned state.

**Suggested fix:** Explicitly check `rc == 0` after `ls-tree`. If it fails but `branch_exists` was True, **abort the push entirely** (return False) — do not fall through to the "branch doesn't exist" path. Or: in the else branch, also push as a new branch (`commit-tree` without `-p`).

**Currently this can be triggered without any concurrency at all on a fresh setup.**

**Closes:** H1 in `findings.md`. **See PR 2 in `pr-roadmap.md`.**

### T-CRIT-2. `send_message` silently drops the message after 3 push failures

**File:** `src/agentweave/transport/git.py:166-176`

After exhausting the retry loop, `_push_file` returns `False`. The caller chain (`MessageBus.send` → `messaging.py:158` → just logs and returns `False`) does not buffer, queue, or write to a local outbox. The user's text is **gone**. Because messages are not staged locally before the push (the LocalTransport path is not used as a fallback for the git transport), there is no recovery path: re-typing the message is the only option. There is also no detection between "transient" failures (worth retrying) and "permanent" failures (the remote is gone). The error string match `"non-fast-forward" in err or "rejected" in err` is loose — many transient network errors return neither phrase, so the function returns False on the first attempt without retrying.

**Suggested fix:** A local outbox (file in `.agentweave/outbox/`) is the standard solution. Write the message locally first, then attempt the push; a separate background process retries pending outbox entries. AGENTS.md says the framework is "safe under concurrent access" — this path violates that.

**Closes:** H2 in `findings.md`. **See PR 2 in `pr-roadmap.md`.**

### T-CRIT-3. Unhandled `json.JSONDecodeError` if Hub returns non-JSON body with 2xx status

**File:** `src/agentweave/transport/http.py:97-100`

The `try` block catches `HTTPError` and `URLError` only. If the Hub (or, more commonly, a reverse proxy in front of the Hub) returns `200 OK` with an HTML error page (e.g. nginx 502 error page, maintenance screen, captive portal response), `json.loads(raw)` raises `json.JSONDecodeError`. This is **not a `RuntimeError`**, so it is **not caught** by any of the surrounding `except RuntimeError` blocks in `send_message`/`get_pending_messages`/etc. The exception propagates up and the agent process dies with a stack trace. AGENTS.md emphasizes "resilient to network failures" — this is a malformed-response failure mode that is not handled.

**Suggested fix:** Catch `json.JSONDecodeError` and `ValueError` in `_request`; raise a `HubTransportError` with classification `"hub_invalid_response"`.

**Closes:** H6 in `findings.md`. **See PR 2 in `pr-roadmap.md`.**

### T-CRIT-4. `HubTransportError` message includes full response body — likely log/secret leak

**File:** `src/agentweave/transport/http.py:111-113`

```python
raise HubTransportError(
    f"Hub API {exc.code}: {body_text}", classification, status_code=exc.code
) from exc
```

`body_text` is the **entire raw body** of the error response, decoded with `errors="replace"`. A misconfigured Hub, debug-mode Hub, or a reverse proxy that echoes request data (headers, query string with `api_key`) will leak secrets into the structured log file (`events.jsonl`). The API key travels in the query string on GET requests (`http.py:81-84`), so any Hub error page that includes the request URL in its HTML will write the API key to disk.

**Suggested fix:** In `_transport_error_data`, truncate `body_text` to e.g. 200 chars and redact `api_key=` query parameters. Better: don't put `body_text` in the exception message at all — store it as an attribute, and let the caller choose what to log.

**Closes:** S7 in `findings.md`. **See PR 3 in `pr-roadmap.md`.**

### T-CRIT-5. No `Content-Length` / size cap on response — memory blowup risk

**File:** `src/agentweave/transport/http.py:97-100`

`resp.read()` reads the entire response body into memory with no limit. A misbehaving (or hostile, if a MITM can swap DNS) Hub that returns a multi-GB payload will OOM the agent. The watchdog polls every 5s, so this is a fast DoS path. There is no `maxsize` argument and no streaming/chunked processing.

**Suggested fix:** Read with a cap (e.g. 10 MB) using a custom file-like wrapper, or use `urllib.request` with a custom handler that enforces a limit.

**Closes:** S10 in `findings.md`. **See PR 3 in `pr-roadmap.md`.**

---

## Concurrency issues

### T-CONC-1. `send_message` writes non-atomically (LocalTransport)

**File:** `src/agentweave/transport/local.py:23-26`

`save_json` (`utils.py:87-95`) opens the target file in `"w"` mode and writes directly. If two agents on the same machine call `send_message` for the **same** message_id (unusual but possible if a retry is triggered from another process) the writes are torn — the second writer's content may be incomplete. For **different** message_ids there's no conflict, but a reader iterating `MESSAGES_PENDING_DIR.glob("*.json")` in `get_pending_messages` may catch a half-written file. `load_json` catches `JSONDecodeError` and returns None, so the message is silently dropped from that poll. At-least-once delivery still holds on the next poll, but it is not visible to a synchronous read pattern (e.g. `mcp_server` tools called immediately after `send_message`).

**Suggested fix:** Write to a temp file in the same directory, then `os.replace()` (on Windows: ensure the file is closed first, which the `with` block guarantees).

**Closes:** M8 in `findings.md`. **See PR 3 in `pr-roadmap.md`.**

### T-CONC-2. `archive_message` is a read-modify-delete with no locking and no atomicity

**File:** `src/agentweave/transport/local.py:38-53`

1. Loads pending file.
2. Sets `read=True`/`read_at`.
3. Writes archive file (non-atomic).
4. Unlinks pending.

Crash between 3 and 4 → the message exists in **both** pending and archive (the `read` flag is set on the archive copy only). Next `get_pending_messages` still returns it from pending. The caller is told `False` from step 4, may retry, and the second iteration will set `read=True` again on a fresh archive write and (if it succeeds) finally delete pending. The final state is consistent, but the watchdog/inbox may see the same message twice in the meantime.

This violates the project rule in AGENTS.md "Always use locking: Task modifications must use `with lock("name"):`" — though strictly the rule names tasks, the same race exists for messages. `LocalTransport` is the only transport in the codebase that touches the FS for messages, and it imports nothing from `locking.py`.

**Closes:** M9 in `findings.md`. **See PR 3 in `pr-roadmap.md`.**

### T-CONC-3. `get_active_tasks` has the same TOCTOU pattern

**File:** `src/agentweave/transport/local.py:60-68`

Same fix needed: no locking, no atomic file reads.

### T-CONC-4. `_save_seen_set` is a non-atomic, read-modify-write race on the seen file (GitTransport)

**File:** `src/agentweave/transport/git.py:182-192`

Two agents on the same machine both calling `archive_message` for different message_ids:
1. Agent A: `_get_seen_set` returns {x}.
2. Agent B: `_get_seen_set` returns {x} (stale, A's update not visible yet).
3. Agent A: adds y, writes {x, y}.
4. Agent B: adds z, writes {x, z} — **y is lost from the seen set**.

The message y will be **re-delivered on every poll forever**. This is a real, observable bug for the git transport when multiple agent processes share a machine. The `_get_seen_set` and `_save_seen_set` operations need the same `with lock("git-seen-{agent}")` wrapping the project already uses for tasks.

**Closes:** M11 in `findings.md`. **See PR 2 in `pr-roadmap.md`.**

### T-CONC-5. `archive_message` walks every file on the branch for every archive call — O(N) per call

**File:** `src/agentweave/transport/git.py:281-305`

Not a concurrency bug, but combined with the linear scan in `get_pending_messages` (line 271) and the lack of any local cache, the git transport becomes O(N²) in the number of messages on the branch per poll. The `_fetch()` call on every `archive_message` is also a network round-trip per archive. In a busy project with thousands of files, this is a real perf cliff.

**Closes:** Listed in T-PERF-1.

### T-CONC-6. `sync_local_jobs` matches 409 by string-fragment in the exception message

**File:** `src/agentweave/transport/http.py:582-602`

```python
if "409" in str(exc) or "Conflict" in str(exc):
```

This will falsely match any error message that happens to contain "409" or "Conflict" (e.g. a Hub error that says "conflict with concurrent modification: 409 retries later"). The `HubTransportError` already exposes `.status_code` as a structured attribute — use that.

Worse: if the exception message format ever changes, the dedup logic silently breaks and jobs get duplicated on the Hub.

**Closes:** Listed in T-MED-1.

---

## GitTransport-specific

### T-GIT-1. `_iso_compact` uses SECOND precision, not millisecond as the docstring claims

**File:** `src/agentweave/transport/git.py:50-52`

The docstring at lines 9-13 says `{iso_ts}` but the implementation is `strftime("%Y%m%dT%H%M%SZ")` — second precision. Within the same second, on the same `(from, to)` pair, the filename is differentiated only by the 6-hex-char UUID prefix (16M combinations). Collisions are unlikely but not impossible for chatty agents. A burst of 10 messages in the same second from the same pair has roughly a 1-in-50,000 collision chance per pair; not catastrophic, but the docstring is wrong.

**Suggested fix:** Either add `%f` (microseconds) to the format string, or use the full 32-char UUID. Six hex chars is also an unusual truncation of a UUID4.

**Closes:** M13 in `findings.md`. **See PR 2 in `pr-roadmap.md`.**

### T-GIT-2. `_push_file` does `hash-object -w` on every retry — wasteful and racy

**File:** `src/agentweave/transport/git.py:114-176`

On attempt 1 the blob is written to the local object store. On attempt 2 we write it again. `hash-object` is content-addressed and idempotent, but it still walks the file. Minor.

### T-GIT-3. `_fetch` has no timeout

**File:** `src/agentweave/transport/git.py:92-95`

`git fetch` can hang indefinitely if the remote is reachable but unresponsive. The watchdog's outer `try/except` catches the eventual exception (after the watchdog's own `poll_interval` of 10s and any watchdog startup wait), but the `subprocess.run` itself can block the agent for arbitrarily long. This is a watchdog-killer in the field.

**Closes:** M7 in `findings.md`. **See PR 2 in `pr-roadmap.md`.**

### T-GIT-4. `read_remote_file` returns None on `json.JSONDecodeError` — good, but masks the failure

**File:** `src/agentweave/transport/git.py:104-112`

A corrupted file on the branch is silently skipped. For messages this means the recipient never sees them and never knows they were skipped. The seen set is also never updated, so the corrupted file will be re-read on every poll forever (wasted work). Consider logging a warning the first time a file is seen as corrupted, then move it to a `.corrupt/` subdir on the branch to quarantine it.

### T-GIT-5. Task status update parsing is fragile

**File:** `src/agentweave/transport/git.py:340-352`

The status file naming convention is `{task_id}-status-{new_status}-{iso_ts}.json`. The parser uses a regex `^(.+?)-\d{4}` to isolate the status from the timestamp. This assumes the task_id contains no digit-4-prefixed substring (UUIDs start with hex digits, so a task_id like `task-4b8a1f` will be misparsed). The audit couldn't construct a definitive collision but the regex is brittle.

**Suggested fix:** Use a structured encoding in the filename (e.g. `{task_id}__status__{new_status}__{iso_ts}.json` with double-underscore separators) or put the status update inside a single JSON envelope with a `kind` discriminator.

**Closes:** M12 in `findings.md`. **See PR 2 in `pr-roadmap.md`.**

### T-GIT-6. `get_active_tasks` filters by `status not in (completed, approved, rejected)` but does not re-filter after applying the status map

**File:** `src/agentweave/transport/git.py:360-362`

If a task is created with `status="pending"` and the only status update is to `"approved"`, the line `if data.get("status") not in ("completed", "approved", "rejected")` correctly excludes it. But if a task is created with `status="completed"` directly (a common pattern for "I already finished this"), the filtering at line 362 only checks `data.get("status")` (the value from the file) — it does not consult `status_map`. This is a minor inconsistency: a task file with `status="approved"` is filtered out, but a task file with `status="approved_rejected"` (which is not in the filter list) would be incorrectly included.

### T-GIT-7. `archive_message` searches the entire branch for the message_id — O(N) and N file reads per archive call

**File:** `src/agentweave/transport/git.py:289-303`

For a branch with 10,000 messages, every archive triggers 10,000 `git show` invocations. Each is a separate subprocess. This is unworkable at scale.

### T-GIT-8. `_run_git` has no timeout on subprocess.run

**File:** `src/agentweave/transport/git.py:55-65`

Any hung git operation hangs the calling thread. For the watchdog this is fatal; for the CLI it just hangs the user. Set a timeout (e.g. 30s) and surface as a transport error.

### T-GIT-9. `get_active_tasks` will see its own status updates via `_fetch()` immediately after writing them, but the seen-set model for tasks is not implemented

**File:** `src/agentweave/transport/git.py:341-365`

Tasks on git transport are at-least-once-delivered, like messages, but `get_active_tasks` returns the same task every poll. The watchdog at `watchdog.py:256-263` only fires on the **set difference** (`current_tasks - self.known_tasks`), so once a task is in `known_tasks` it doesn't re-fire. But the **status** of a task can change via status-update files. There is no mechanism in the git transport to detect a status change. The recipient has to explicitly call `get_active_tasks` again. This isn't strictly a bug but it's a design choice the docs don't call out.

### T-GIT-10. No handling of CRLF / `core.autocrlf`

**File:** `src/agentweave/transport/git.py:38-46`

Git on Windows with `core.autocrlf=true` will rewrite `\n` to `\r\n` in text files. The agent writes `json.dumps(message_data, indent=2)` (LF), and if the user's git config is set to convert on checkout/checkin, the JSON could end up on the orphan branch with mixed line endings. The orphan branch isn't checked out, so this only matters if the file is later read with line-aware tools. Mostly harmless for `json.loads` (which accepts CRLF), but worth flagging.

---

## HttpTransport-specific

### T-HTTP-1. Timeout is hard-coded to 10s — no per-request override

**File:** `src/agentweave/transport/http.py:98`

Large messages (e.g. file embeds) may legitimately take longer than 10s. Some Hub operations (Hub shutdown, long DB migrations) may temporarily take longer. The constant is in the right place for safety, but it should be configurable via transport.json for ops scenarios.

### T-HTTP-2. No retry logic for 5xx, 429, or transient network errors

**File:** `src/agentweave/transport/http.py` (entire file)

Every transient error (a single dropped packet, a 502 from the load balancer, a 429 from the Hub rate limiter) causes the message to be lost. AGENTS.md emphasizes "resilient to network failures" — this is the single biggest gap.

**Suggested fix:** At minimum, retry on 502/503/504/429 with exponential backoff and respect the `Retry-After` response header. For 5xx, three attempts is reasonable. For 429, honor `Retry-After` and cap at 5 attempts.

**Closes:** H3 in `findings.md`. **See PR 2 in `pr-roadmap.md`.**

### T-HTTP-3. `URLError.reason` is str-compared against `"timed out"` in lower case

**File:** `src/agentweave/transport/http.py:114-117`

This is fragile: Python's `socket.timeout` and `TimeoutError` exception messages vary by Python version and platform. On Python 3.10+ on Linux the message is `"timed out"`; on Windows it can be `"timed out"` or `"A connection attempt failed..."` depending on the failure mode. Use `isinstance(exc.reason, (socket.timeout, TimeoutError))` instead of substring matching.

### T-HTTP-4. No `User-Agent` header

**File:** `src/agentweave/transport/http.py:97-100`

Default UA is `Python-urllib/3.x`. Some hardened Hub deployments reject unknown user agents. Set `User-Agent: agentweave-ai/0.37.0` to be polite and to make server-side logs more useful.

**Closes:** Q11 in `findings.md`. **See PR 3 in `pr-roadmap.md`.**

### T-HTTP-5. `urllib.request.urlopen` follows redirects by default, but the `Authorization` header is NOT re-sent on cross-host redirects

**File:** `src/agentweave/transport/http.py:98`

This is documented stdlib behavior. If the Hub ever does a 30x to a different host (e.g. SSO callback, CDN URL), the auth header is stripped. This is rarely an issue for a well-behaved Hub but is a foot-gun. Set a custom redirect handler (`HTTPRedirectHandler`) that aborts on cross-host redirects, or at least re-adds the auth header.

**Closes:** Q9 in `findings.md`.

### T-HTTP-6. No exponential backoff on `URLError`/`hub_unreachable`

**File:** `src/agentweave/transport/http.py:65-117`

The watchdog's outer try/except catches and logs the error, but the next poll is `poll_interval` (5s) away. A Hub that just bounced will see retries at exactly `poll_interval` regardless of `Retry-After`. A modest in-method backoff (e.g. 0s, 1s, 2s, 4s) for the same agent invocation would smooth this out.

### T-HTTP-7. `send_message` body mapping drops fields

**File:** `src/agentweave/transport/http.py:127-138`

Only `from, to, subject, content, type, task_id, id, timestamp` are forwarded. Any other field on `message_data` (e.g. `read`, `read_at`, custom metadata) is silently dropped. If the caller added extra context for another transport, it's lost. Not a bug per se, but a leaky abstraction.

### T-HTTP-8. `_transport_error_data` falls through to a generic `"transport_error"` classification for non-`HubTransportError` exceptions

**File:** `src/agentweave/transport/http.py:45-49`

If `_request` ever raises something other than `HubTransportError` (which it currently does for `json.JSONDecodeError` — see T-CRIT-3), the log shows `"classification": "transport_error"` with no `status_code`, making the incident hard to triage.

### T-HTTP-9. `push_log` swallows ALL exceptions silently

**File:** `src/agentweave/transport/http.py:466`

The comment says "never logs a log failure" but this means a permanently-broken Hub (e.g. wrong URL, expired key) will produce zero diagnostic output. The watchdog will appear to be working fine; logs will simply never arrive. Consider at least counting failures and exposing a diagnostic (`agentweave doctor`).

### T-HTTP-10. `sync_local_jobs` is called from `get_transport()` every time the transport is instantiated

**File:** `src/agentweave/transport/http.py:582-602`

`get_transport()` is called from many places (MCP server startup, every CLI command, every watchdog tick). The `_find_transport_config()` call returns the same cached-style config, but a new `HttpTransport` is constructed each time, which triggers `sync_local_jobs()`. This is an N×Hub-job-creation round-trip on every CLI invocation. It should be moved to a one-shot startup hook (e.g. called once per process) or behind a `lockfile` so only the first instance syncs.

---

## LocalTransport-specific

### T-LOC-1. `save_json` has no `os.replace` atomicity

See T-CONC-1. The `MESSAGES_PENDING_DIR` and `TASKS_ACTIVE_DIR` are shared between multiple agents on the same machine — atomicity matters.

### T-LOC-2. `send_task` is the same as `send_message` for the file creation — no `os.replace`

**File:** `src/agentweave/transport/local.py:55-58`

But `cli.py:1276` does `acquire_lock(f"task_{args.task_id}", timeout=10)` before calling into task code, so there's an outer lock at the CLI level. The transport itself doesn't enforce it, so any direct caller (MCP server, watchdog) is unprotected.

### T-LOC-3. No file permissions hardening

`save_json` uses default umask. On Linux, this typically gives 0644 (world-readable) for message files that may contain sensitive content (auth tokens, code, internal communications). On macOS it's similar. On Windows the default ACL grants read access to all users. The framework documents `aw_live_*` API keys as secrets (`AGENTS.md` "API key format: aw_live_{random32} — never commit keys") but the same machine-local message files don't get similar treatment.

**Suggested fix:** `os.open(filepath, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)`. On Windows, ACLs need a separate code path; at minimum, on POSIX do this.

**Closes:** S11 in `findings.md`. **See PR 3 in `pr-roadmap.md`.**

### T-LOC-4. Archive directory is unbounded

`MESSAGES_ARCHIVE_DIR` grows forever. After a year of usage with even moderate message volume, this is a real disk concern. There is no archival/rotation policy. Suggest a `--archive-retention-days` config option, or auto-prune archive entries older than N days on startup.

### T-LOC-5. No `validate_message`/`validate_task` on the transport layer

The transport trusts whatever the caller passes. `cli.py` and `mcp/server.py` validate before calling, but the transport itself is a leaky trust boundary — any future caller that forgets to validate will write arbitrary content to disk. A bad message with `id="../../etc/passwd"` would create a file outside the expected directory.

**Suggested fix:** At the transport layer, validate `message_id`/`task_id` against `AGENT_NAME_RE` (extended to IDs) before constructing the path. Reject anything with `..`, `/`, `\`, or NUL. AGENTS.md critical rule #1 says "Use `AGENT_NAME_RE`" — currently the transport layer doesn't.

**Closes:** S2 in `findings.md`. **See PR 3 in `pr-roadmap.md`.**

### T-LOC-6. `archive_message` doesn't delete the file on archive write failure

If `save_json(archive_path, data)` fails (e.g. disk full, permission denied), the function returns `False` and the pending file is left in place. The next archive call will retry and the message will be archived later. This is correct, but the caller in `messaging.py:223` and the watchdog both treat `False` as "archive failed; do not mark as read" — they may stop processing entirely. The caller has no way to distinguish "not found" from "write failed" from "already archived".

---

## BaseTransport / factory issues

### T-ABC-1. Methods that "raise NotImplementedError" but are not abstract are misleading

**File:** `src/agentweave/transport/base.py:43-95`

`create_job`, `list_jobs`, `get_job`, `update_job`, `delete_job`, `fire_job`, `register_session` all raise `NotImplementedError` from a non-abstract method. From a type-checker's perspective, the base class declares them as returning concrete types. From a runtime perspective, calling them on a `LocalTransport` raises — but the error is far from the call site. The MCP tool layer (`mcp/server.py`) has to do `isinstance` / `getattr` checks to avoid this. Either make them abstract (forcing the base class to formalize the contract) or have the base implementation return a sensible default (e.g. `False`, `None`).

### T-ABC-2. `push_session` and `push_roles_config` return `False` for non-HTTP transports

**File:** `src/agentweave/transport/base.py:67-73`

This is silent: if a user has HTTP transport configured but the Hub is down, the sync fails with no error to the user. The function returns False, the caller (e.g. `Session.save` in `session.py`) has to check the return. There's no logging of the failure at the base class level. Consider a default `logger.warning` here.

### T-ABC-3. `archive_message` contract is unclear

**File:** `src/agentweave/transport/base.py:23-25`

The docstring says "Mark a message as read / archived." For `LocalTransport` it deletes the pending file and writes an archive file. For `GitTransport` it adds to a local seen set. For `HttpTransport` it calls Hub PATCH. The semantics are wildly different (filesystem delete vs local-only state vs server-side state). The contract is the same word, three behaviors. A type signature alone (`bool`) cannot distinguish "the recipient's transport knows it's read" from "the message has been moved to a different directory" from "a server has been told to mark it as read". Consider returning an enum (`ArchiveResult.READ_LOCAL`, `READ_REMOTE`, `READ_BY_HUB`).

### T-ABC-4. The 6 abstract methods don't include `pull` / `sync`

The watchdog (`watchdog.py:855`) calls `self.transport._fetch()` and `self.transport.list_remote_filenames()` — these are not in the ABC, so the watchdog has to do `getattr`/ducktype checks (`type: ignore[union-attr]`). For a class designed as a "transport" abstraction, polling is a first-class concern and should be abstract.

### T-FAC-1. `get_transport` is called many times and constructs a new transport each time

**File:** `src/agentweave/transport/config.py:43-96`

This means `sync_local_jobs` is called every CLI invocation, and any transport-level state (HTTP connection pooling, git fetch state) is recreated. Consider a module-level cache (`functools.lru_cache(maxsize=1)`) keyed on `transport.json` mtime, or a singleton pattern with explicit `close()` on shutdown. The current behavior is wasteful and surprising.

### T-FAC-2. `_find_transport_config` walks up from CWD looking for `.agentweave/transport.json`

**File:** `src/agentweave/transport/config.py:11-40`

This is intended to find the project from any CWD (MCP servers run from arbitrary dirs). But it also means that if a user `cd`s to a directory with **no** `.agentweave/` ancestor, they get `LocalTransport` for the local `~/.agentweave/shared/...` directories. This is potentially confusing: a user in `/tmp/foo` with no project but with `transport.json` in their home directory (`~`) will use HTTP transport. This is a foot-gun. Consider requiring the config to be in a directory that contains an `AGENTS.md` or other project marker, or emit a clear warning when a config is found via parent-walk.

### T-FAC-3. `sync_local_jobs` is called inside `get_transport()` with a bare `contextlib.suppress(Exception)`

**File:** `src/agentweave/transport/config.py:88-91`

Any error in job sync (auth failure, network down, schema mismatch) is completely silent. The user has no way to know their local jobs aren't syncing. The watchdog will not retry; the user will only notice when they check the Hub dashboard.

### T-FAC-4. HTTP transport config doesn't validate that `url`, `api_key`, and `project_id` are non-empty

**File:** `src/agentweave/transport/config.py:79-86`

If `transport.json` is missing any of these (e.g. user typo'd the field name), `HttpTransport` is constructed with `url=""` and `api_key=""`. Every request goes to `http:///api/v1/...` and the auth header is `Authorization: Bearer `. The error from the request is a generic `URLError`. The user has no clue what's wrong.

### T-FAC-5. `_find_transport_config` re-reads and re-parses transport.json on every call

**File:** `src/agentweave/transport/config.py:11-40`

Combined with the lack of caching in `get_transport`, every CLI invocation reads the file at least twice (once for fast path, once for parent walk). For a heavily-used CLI, this is acceptable, but consider caching.

### T-FAC-6. `save_json` is non-atomic — same problem as in the transport layer

**File:** `src/agentweave/transport/config.py` (not direct, but `cli.py:2256` calls `save_json(TRANSPORT_CONFIG_FILE, config)` with the same non-atomic `utils.save_json`)

The factory doesn't write the file (the CLI does), but the CLI calls `save_json(TRANSPORT_CONFIG_FILE, config)` in `cli.py:2256` and `cli.py:2195` with the same non-atomic `utils.save_json`. If the agent crashes mid-write, the config could be left truncated/invalid. A torn config would be caught by `load_json` (returns None) → falls back to `LocalTransport`, so it's self-healing, but the user may be confused about why their git/http transport is no longer active.

---

## Test coverage

### `tests/test_transport_local.py` (88 lines)

Covers happy path only. Missing:
- Concurrent writes to the same file (use `threading`)
- `archive_message` with archive-write failure (mock `save_json` to fail)
- `archive_message` crash-mid-flight (delete pending between operations)
- Path traversal attempts in `message_id`
- File permissions (0600 expectation)
- Empty `to` field handling
- `get_pending_messages` while a write is in progress (file locked or partial)
- Archive directory cleanup/retention

### `tests/test_http_transport.py` (103 lines)

Covers happy path. Missing:
- **No test for 5xx retry** (because the code has no retry — but the test should assert this and fail).
- **No test for 429 / `Retry-After` handling.**
- **No test for HTML/non-JSON 200 response** (would currently crash the test with `JSONDecodeError`).
- **No test for large response body** (memory cap).
- **No test for cross-host redirect** (Authorization header stripping).
- **No test that `api_key` is not in the URL** (only the Authorization header).
- **No test for `HubTransportError` body redaction in logs.**
- **No test for `URLError` reason string matching on different platforms.**
- **No test for `sync_local_jobs` deduplication on 409.**
- **No test for `is_agent_registered` / `get_agent_registration` against a 401 response.**

### `tests/test_git_transport.py`: DOES NOT EXIST

The git transport has zero test coverage. Given the data-loss bugs above, this is a critical gap. Missing tests:
- `branch_exists_on_remote` with no remote configured
- `branch_exists_on_remote` with offline remote
- `_push_file` with the ls-tree race (mock `ls-tree` to return rc != 0 after `ls-remote` succeeds)
- `_push_file` retry exhaustion
- `_push_file` NFF recovery (mock push to return NFF, then succeed on retry)
- Filename collision scenarios
- Corrupted JSON on the branch (return value, no crash)
- Seen-set concurrent updates (threading)
- Cluster-prefixed addressing round-trip
- Status update file parsing for task_id containing digits

**Closes:** T1 in `findings.md`. **See PR 12 in `pr-roadmap.md`.**

### `tests/test_diagnostics.py:166-190`

One good test for 401 classification. Should be expanded to cover all `classification` values (timeout, unreachable, project_missing, api_error, invalid_response if added).

### `tests/test_locking.py`

Tests the lock primitive itself but no test verifies that the transport layer **uses** the lock. A meta-test asserting "LocalTransport has a reference to `locking.lock`" or "all `BaseTransport` write methods are wrapped in `with lock(...)`" would catch the missing-locking class of bug.

**Closes:** T2 in `findings.md`. **See PR 12 in `pr-roadmap.md`.**

### No `tests/test_transport_config.py`

Factory is untested. Missing:
- Malformed JSON falls back to LocalTransport
- Unknown `type` falls back to LocalTransport
- HTTP transport rejects empty `url`/`api_key`/`project_id`
- `transport.json` in parent directory is found via walk-up
- Walk-up stops at filesystem root

### No `tests/test_transport_abc.py`

The contract of `BaseTransport` is informal. There's no test that the 6 abstract methods are correctly enforced (i.e. trying to instantiate a subclass missing one fails).

---

## Quick wins

1. **Add `os.replace` atomicity to `save_json`** in `utils.py:87`. A few lines of code, fixes a class of bugs across all three transports.
2. **Add a timeout to `_run_git`** in `git.py:55-65`. `subprocess.run(..., timeout=30)` plus a `subprocess.TimeoutExpired` handler that returns `(124, "", "git timed out")`. Prevents the watchdog from hanging on a stalled `git fetch`.
3. **Add basic retry+backoff to `HttpTransport._request`** for 5xx and 429. Even 2 attempts with `Retry-After` honoring would close the most common silent-data-loss path.
4. **Catch `json.JSONDecodeError` in `HttpTransport._request`** and raise `HubTransportError` with classification `"hub_invalid_response"`. Five lines of code, prevents stack-trace crashes on misbehaving Hub responses.
5. **Validate IDs in `LocalTransport.send_message` and `archive_message`** against the same `AGENT_NAME_RE` regex (extended to allow UUID chars).
6. **Wrap `_get_seen_set`/`_save_seen_set` in `with lock(f"git-seen-{agent}")`** in `git.py:300-302`. Fixes the read-modify-write race for multi-agent same-machine scenarios.
7. **Truncate `body_text` and redact `api_key=` query strings** from `HubTransportError` message and structured log data.
8. **Atomic write of `transport.json`** in the CLI.
9. **Add `is_locked`/lock acquisition to the watchdog's `_check_once_remote` path** to prevent multiple watchdogs running on the same machine.
10. **A single `tests/test_transport_git.py`** with the data-loss cases above would catch all the critical git bugs in one PR. Highest priority test addition in the codebase.
11. **Module-level cache for `get_transport()`** with a TTL of e.g. 30s, keyed on `transport.json` mtime. Eliminates the `sync_local_jobs` N-rounds-per-invocation problem.
12. **Set `User-Agent: agentweave-ai/<version>` on the `Request` object** in `http.py:92-96`.
13. **Read `self.api_key` once and store a redacted form** (e.g. `aw_live_***` keeping first 8 + last 4 chars) for any error message construction.

---

## Summary

| Severity | Count |
|---|---|
| Critical (data corruption / loss / hang) | 5 |
| Concurrency issues | 6 |
| GitTransport-specific | 10 |
| HttpTransport-specific | 10 |
| LocalTransport-specific | 6 |
| BaseTransport / factory | 6 + 6 = 12 |
| Test coverage | 6 areas |
| Quick wins | 13 |

**The single most important fix is T-CRIT-1** — the `ls-tree` race that can wipe the entire orphan branch. This can be triggered on a fresh setup with no concurrency at all.

**The second most important is T-CRIT-2** — the silent message drop after 3 push failures. Users re-typing messages with no idea why they didn't arrive.

**The third is T-CONC-4** — the seen-set race, which causes messages to be re-delivered forever when two agents share a machine.

All three are in PR 2 of `pr-roadmap.md`.
