# Audit Report 02 — Hub Backend

**Scope:** All Python files in `hub/hub/`
**Date:** 2026-06-12
**Auditor:** opencode (MiniMax-M3) via Task tool, subagent_type=explore
**Method:** Read whole files, cross-reference with `hub/tests/`, identify auth bypass, BOLA, SQL injection, race conditions, and architectural problems.

## Files in scope

```
hub/hub/
├── main.py
├── mcp_server.py
├── db/
│   ├── engine.py
│   ├── models.py
│   ├── session.py
│   └── migrations/
├── api/v1/
│   ├── agents.py
│   ├── messages.py
│   ├── tasks.py
│   ├── questions.py
│   ├── events.py
│   ├── logs.py
│   ├── agent_chat.py
│   ├── agent_trigger.py
│   ├── jobs.py
│   ├── setup.py
│   ├── session_sync.py
│   ├── instructions.py
│   ├── status.py
│   └── __init__.py
├── schemas/
├── sse.py
├── scheduler.py
└── config.py
```

---

## CRITICAL security bugs (data leak / auth bypass)

### HUB-C1. SPA fallback leaks the live API key to any unauthenticated request

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\main.py:66-99`

```python
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    if full_path.startswith("api/") or full_path == "health":
        raise HTTPException(404)
    ...
    api_key_value = settings.aw_bootstrap_api_key
    ...
    _res = await _db.execute(
        _select(_ApiKey).where(_ApiKey.revoked == False).limit(1)
    )
    if _row:
        api_key_value = _row.id            # <-- the LIVE key
    ...
    config = json.dumps({"apiKey": api_key_value, "projectId": project_id_value})
    script = f"<script>window.__AW_CONFIG__={config};</script>"
    html = html.replace("</head>", f"{script}</head>")
    return HTMLResponse(html)
```

**Attack vector:** The catch-all `GET /{full_path:path}` route is registered **after** the v1 router and has **no `Depends(get_project)`**. The `serve_spa` handler does not call `get_project`; it bypasses auth entirely and then queries the DB directly for any non-revoked key, embedding it in the served HTML. Anyone with network access to the Hub (e.g., a Docker container on a public host, a misconfigured reverse proxy, a co-tenant in a shared LAN) can `curl http://hub:8000/anything` and receive a fully privileged API key in the response body.

**Suggested fix:** Move the `<script>__AW_CONFIG__</script>` injection behind a `/api/v1/setup/token` fetch — the SPA already has this endpoint, it just needs to call it on first load instead of receiving the key in HTML.

**Closes:** C1 in `findings.md`. **See `pr1-spa-key-leak.md` for the full fix plan.**

### HUB-C2. Path traversal in role/markdown template loader

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\api\v1\agents.py:495-533` and exposed by `agents.py:875-890` (`/api/v1/agents/context?role=...`).

```python
async def _load_role_content(role: str, project_id: str, db: AsyncSession) -> str:
    role_file = Path(".agentweave/roles") / f"{role}.md"
    if role_file.exists():
        role_content = role_file.read_text(encoding="utf-8")
    else:
        bundled = Path(__file__).parent.parent.parent / "data" / "roles" / f"{role}.md"
        ...
        pkg_file = (... / "src" / "agentweave" / "templates" / "roles" / f"{role}.md")
        ...
            role_content = pkg_file.read_text(encoding="utf-8")
```

**Attack vector:** `get_role_context(role: str, ...)` (line 875) accepts `role` as a raw query string with **no validation** (compare to `get_agent_runtime_context` at line 893 which does enforce `^[^a-zA-Z0-9_-]{1,32}$`). An authenticated user can pass `role=../../etc/passwd` (or absolute-path `role=/etc/shadow`) and the function will `read_text()` any matching `.md` file accessible to the Hub process. `Path(...) / "/absolute/path"` is documented to reset to the absolute root, so a value of `/etc/shadow` becomes `Path("/etc/shadow.md")`. The endpoints that surface this are `/api/v1/agents/context?role=...` and `/api/v1/agents/agent-context?agent=...` (the latter validates `agent` but its role iteration at line 700 calls `_load_role_content(role, ...)` with attacker-influenced role IDs from `ProjectRolesConfig`).

**Suggested fix:** Add `if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", role): raise 400` to `_load_role_content` (and to `get_role_context`).

**Closes:** S1 in `findings.md`.

### HUB-C3. API key accepted via query string — leaks into logs, browser history, and proxies

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\auth.py:18,26`

```python
token: Optional[str] = Query(None),  # for EventSource SSE connections
...
api_key = (credentials.credentials if credentials else None) or token
```

**Attack vector:** Any authenticated user can pass `?token=aw_live_xxx` instead of an `Authorization: Bearer` header. API keys then appear in:
- uvicorn access logs (`GET /api/v1/events?token=aw_live_... 200`)
- nginx / traefik access logs
- browser history and referer headers (SSE is a `GET`)
- any reverse proxy in the path

This makes key rotation a fire-drill the moment any production log aggregator is misconfigured.

**Suggested fix:** Restrict the `?token=` fallback to **only** the SSE endpoint and require a short-lived cookie/header for everything else; or remove it entirely and require the JS client to use `EventSource` polyfill that sets headers.

**Closes:** S3 (server half) in `findings.md`.

### HUB-C4. Mass assignment lets clients pick message/task/job IDs and backdate timestamps

**Files:**
- `schemas/messages.py:19-21` — `id: Optional[str] = None`, `timestamp: Optional[str] = None`
- `schemas/tasks.py:33-34` — `id: Optional[str] = None`, `created_at: Optional[str] = None`
- `schemas/jobs.py:17` — `id: Optional[str] = None`

**Attack vector:**
1. `id`: An attacker can specify an ID of an existing record. `messages.py:28` and `tasks.py:59` blindly insert with `msg_id = body.id or f"msg-{short_id()}"`. The DB primary key collision surfaces as a 500 (or, in `jobs.py`, a hand-rolled 409). On PostgreSQL this is "just" an availability bug; on SQLite the whole DB write transaction is rolled back for that request.
2. `id` collision *with own content* still poisons analytics (you can overwrite an ID you previously sent).
3. `timestamp`/`created_at`: Attackers can backdate messages, tasks, etc. — useful for spoofing audit trails, expiring jobs, or gaming any "since X" window logic.
4. `MessageCreate` also has `populate_by_name=True`, so JSON keys `id` and `timestamp` are silently accepted without the alias surface being obvious.

**Suggested fix:** Remove `id` / `timestamp` / `created_at` from the Create schemas. The server should be the sole source of truth. If the CLI genuinely needs a client-supplied ID, gate it behind an explicit `client_supplied_id: bool` flag and a separate `idempotency_keys` table.

**Closes:** S5 in `findings.md`.

### HUB-C5. No input length limits anywhere → DB DoS and SSE flood

**Files (representative):**
- `schemas/messages.py:15-17` — `subject: Optional[str]` (DB: `String(256)`), `content: str` (DB: `Text`, unbounded)
- `schemas/questions.py:11` — `question: str` (Text, unbounded), `answer: str` (Text, unbounded)
- `schemas/agents.py:50-56` — `message: Optional[str]`, `content: str` (Text, unbounded)
- `schemas/logs.py:21-25` — `event_type: str`, `agent: Optional[str]`, `data: Optional[Any]` — no length cap, no schema
- `api/v1/session_sync.py:30` — `data: Dict[str, Any]` — no depth or size cap
- `api/v1/instructions.py:40` — `content = body.get("content", "")` — unbounded Text
- `api/v1/agent_trigger.py:42-45` — `work_dir: Optional[str]` — unbounded, no validation, no rejection of `..` or `~`
- `api/v1/jobs.py:69-147` — `name`, `message`, `cron` — no max_length

**Attack vector:** A single authenticated POST can write a multi-GB row (`content` field), which is then broadcast verbatim to every SSE subscriber of the project (including the attacker's open tab). The next SSE listener gets the entire payload in memory, then serializes it again, etc. With N concurrent listeners this is an N× amplification vector.

**Suggested fix:** Add `max_length=...` to every `str` field. Cap `data: Dict[str, Any]` size or replace with a stricter sub-model. Reject `work_dir` containing `..` or starting with `~`.

**Closes:** S6, S12 in `findings.md`.

---

## Concurrency bugs

### HUB-CO1. N+1 in MCP `get_inbox` — `1 GET + N PATCH` blocking urllib calls inside the event loop

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\mcp_server.py:121-143`

```python
@mcp.tool()
def get_inbox(agent: str) -> List[Dict[str, Any]]:
    ...
    messages = _hub_request("GET", "/messages", params={"agent": agent})
    for msg in messages:
        try:
            _hub_request("PATCH", f"/messages/{msg['id']}/read")
        except RuntimeError:
            pass
    return messages
```

**Issues:**
1. Synchronous `urllib.request.urlopen` in a tool the framework may run inside the asyncio loop (blocking I/O).
2. One HTTP round trip per message — a 100-message inbox is 101 round trips, easily 10s of seconds. A watchdog that polls this tool frequently will saturate the Hub.

**Fix:** Add a bulk `POST /api/v1/messages/mark-read` (or accept a list of IDs), or move the auto-marking into the `GET /messages` query itself. If a per-message PATCH is required, use `asyncio.gather` with `httpx.AsyncClient`.

**Closes:** M1 in `findings.md`.

### HUB-CO2. `mcp_server._hub_request` is a sync function wrapping sync `urllib`, no thread-pool guarantee

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\mcp_server.py:39-73`

`@mcp.tool()` registers the function. If FastMCP runs sync tools on the event loop (the default for `fastmcp` stdio and SSE transports in some versions), every Hub REST call blocks the entire MCP server. All 20+ tools share that bottleneck.

**Fix:** Use `httpx.AsyncClient` with `asyncio.to_thread` (stdlib) or `asyncio.run_in_executor`, or migrate tools to async signatures.

**Closes:** M2 in `findings.md`.

### HUB-CO3. `_record_job_run_failure` commits inside a request session — possible nested-commit issues

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\api\v1\jobs.py:31-66` (and a similar pattern in `scheduler.py:325-348`)

```python
async def _record_job_run_failure(...):
    ...
    session.add(run)
    await persist_event(...)
    await session.commit()     # <-- commits while caller still has a session open
    return run_id
```

Called from `run_job` (line 409) and from the scheduler. The caller's session has not been committed/rolled back, so a later `await session.commit()` in the caller may try to commit a transaction that's already been split. With SQLite this can cause `InvalidRequestError: This Session's transaction has been rolled back due to a previous exception`. With async sessions and concurrent tasks, this is also a race: two workers can both call `_record_job_run_failure` against the same session.

**Fix:** Return the run data and let the caller commit, or use a separate session explicitly via `async_session_factory()`.

### HUB-CO4. Session commit pattern in `agent_trigger.py:108-119` is dead-code / bug-prone

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\api\v1\agent_trigger.py:88-119`

```python
if latest_hb is None:
    execution_confidence = "queued_no_watchdog_heartbeat"
    watchdog_status = "missing"
else:
    hb_ts = latest_hb.timestamp
    if hb_ts.tzinfo is None:
        hb_ts = hb_ts.replace(tzinfo=timezone.utc)

if latest_hb is not None and hb_ts < stale_cutoff:
    execution_confidence = "queued_watchdog_stale"
    watchdog_status = "stale"
elif latest_hb is not None:
    execution_confidence = "queued_watchdog_healthy"
    watchdog_status = latest_hb.status
```

`hb_ts` is only assigned inside the `else` branch (when `latest_hb is not None`), so the third `if` correctly re-checks `latest_hb is not None`. Functionally OK, but the dead `else:` makes it look like `hb_ts` is in scope. The code is fragile to refactoring.

**Fix:** Refactor to a single chain of `elif`.

### HUB-CO5. `_prune_job_history` runs after every job fire — O(N log N) write per scheduled tick

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\scheduler.py:167-190`

Every fire of a job with >100 runs does a `SELECT id ... OFFSET 100` + `DELETE ... WHERE id IN (...)` inside the same transaction as the new `INSERT`. For a job that fires every minute this is constant DB churn; for backfills, it scales linearly with history size. Not a correctness bug, but should be batched (e.g., once per hour) and use `DELETE ... WHERE fired_at < (SELECT fired_at FROM job_runs ORDER BY fired_at DESC LIMIT 1 OFFSET 100)` to avoid a subquery in PostgreSQL.

### HUB-CO6. `get_db` dependency is correct, but the global `sse_manager` queue is a shared mutable singleton

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\sse.py:13-45`

`SSEManager` is fine for single-process. If anyone ever runs uvicorn with `--workers > 1` (or behind a load balancer that hashes on something other than session), the second worker will never receive broadcasts from the first. The dashboard will appear to "miss" events randomly. This is a deployment gotcha, not a code bug — but it's worth a comment or a Redis-backed manager.

---

## API bugs / wrong behavior

### HUB-AP1. `agent_chat.get_recent_chat` `limit` parameter has no bounds

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\api\v1\agent_chat.py:167-234`

```python
async def get_recent_chat(
    agent: str,
    limit: int = 50,           # <-- no Query(), no ge/le
    ...
):
```

`limit` is silently a query param with **no validation**. A `?limit=999999999` request pulls and in-memory-sorts every Message + AgentOutput for the agent in the project.

**Fix:** `limit: int = Query(50, ge=1, le=500)`.

**Closes:** M14 in `findings.md`.

### HUB-AP2. Missing pagination / N+1 in `list_agents`

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\api\v1\agents.py:96-377`

This endpoint runs **at least 4 queries per agent** (heartbeat, message count, task count, context warning, session started_at) in a loop in Python — classic N+1. With 50 agents that's ~200 round trips to the DB. There is no pagination and no caching.

**Fix:** Use `selectinload` or a single window-function query (e.g. `MAX(timestamp) OVER (PARTITION BY agent)`) to get all of it in 2-3 queries.

**Closes:** M15 in `findings.md`.

### HUB-AP3. `list_messages.history` semantics inverted

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\api\v1\messages.py:55-64`

```python
history: bool = Query(False),
...
if not history:
    q = q.where(Message.read == False)
```

The query param is `history`, but the filter is "include read messages". A bool named `history` that filters unread when `False` is confusing. Either rename to `include_read` or document.

### HUB-AP4. `list_tasks` doesn't honor `task_status` values list — no enum check

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\api\v1\tasks.py:102-117`

The query is `q.where(Task.status == task_status)` with no validation. `?status=foo` returns empty results silently. Inconsistent with `TaskCreate` / `TaskUpdate` validators that enforce `_TASK_STATUSES`.

### HUB-AP5. DateTime serialization is mostly correct, but `since` in `list_logs` and `get_agent_output` silently swallows bad input

**Files:** `api/v1/logs.py:61-66`, `api/v1/agents.py:1089-1094`

```python
if since:
    try:
        since_dt = datetime.fromisoformat(since)
        q = q.where(... > since_dt)
    except ValueError:
        pass            # <-- silently ignored
```

A user passing garbage `?since=garbage` gets the full unfiltered list, not a 400. Should be 422.

### HUB-AP6. `get_message` / `mark_read` use `404` for cross-project access

Already done correctly in `messages.py:91`, `tasks.py:139`, `questions.py:78`, `jobs.py:175`. No issue — keep as is. Documenting because it's a common review nit.

### HUB-AP7. `serve_spa` 404s `api/...` paths but does not handle missing `index.html` gracefully

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\main.py:66-99`

If `UI_DIST / "index.html"` doesn't exist, `read_text()` raises `FileNotFoundError` → 500. Should `raise HTTPException(404)` from inside the `if UI_DIST.exists():` block, or have a fallback.

### HUB-AP8. `event_stream` initial yield is hardcoded

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\api\v1\events.py:54-66`

```python
yield "data: connected\n\n"
while True:
    if await request.is_disconnected():
        break
    try:
        message = await asyncio.wait_for(queue.get(), timeout=30)
        yield message
    except asyncio.TimeoutError:
        yield ": keepalive\n\n"
```

No `id:` lines, no `retry:` directive. If a client reconnects with `Last-Event-ID`, the server can't replay missed events. This is by design (server has no buffer) but worth flagging.

### HUB-AP9. `_hub_request` MCP helper drops context on HTTPError — message truncated at 4 KB

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\mcp_server.py:72-73`

```python
except urllib.error.HTTPError as exc:
    raise RuntimeError(f"Hub API error {exc.code}: {exc.read().decode()}")
```

No `read().decode(errors='replace')`, no length cap. A 500 from the Hub with a giant traceback will be embedded in the error message verbatim. Fine for debugging; bad for log retention.

### HUB-AP10. `mcp_server` `register_session` returns success even when `from_agent` is the same as a configured agent

No collision check (unlike `register_agent` which 409s). A misbehaving agent can hijack a principal's identity by calling `register_session("claude", ...)` and then receiving messages addressed to `claude`. Combined with the "claude" SSE stream being shared, this is a privilege confusion.

**Fix:** Add the same `if name in session_agents: raise 409` check from `register_agent`.

**Closes:** M16 in `findings.md`.

### HUB-AP11. Inconsistent `Content-Type` for SSE

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\api\v1\events.py:69`

`EventSourceResponse` handles this correctly. No issue — just confirming.

### HUB-AP12. `agent_trigger` `work_dir` never validated

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\api\v1\agent_trigger.py:42-45, 124-149`

The server stores `work_dir` nowhere (it isn't even put in the Message row). It's purely a watchdog hint. If the watchdog on the host uses it to spawn a CLI, a malicious value of `work_dir=/etc/cron.d` or `work_dir=/tmp; rm -rf /` could be disastrous. This is a *trust boundary* problem: the Hub is the only line of defense and it does nothing.

**Closes:** S12 in `findings.md`.

### HUB-AP13. `_load_role_content` reads filesystem relative to CWD

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\api\v1\agents.py:507-531` and `_get_session_data` at `agents.py:44-68`

Both functions fall back to `Path(".agentweave/...")` and `Path("..") / ".agentweave" / "session.json"`. In a Docker container this is benign (CWD is fixed at `/app` or similar), but in `python -m hub` from an interactive shell the CWD is whatever the operator typed. If a user starts the Hub from inside a malicious project directory, that project's `session.json` gets read. Combined with HUB-C2 (path traversal), this widens the attack surface considerably.

**Fix:** Either (a) drop the filesystem fallback entirely and require `SessionSyncRequest` from the CLI (the DB-only path), or (b) lock the path to an absolute `HUB_DATA_DIR` env var.

---

## Database / migration issues

### HUB-DB1. `init_db` does not run Alembic migrations — only `create_all`

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\db\engine.py:39-86` and `main.py:21-26`

The lifespan calls `await init_db()` which uses `Base.metadata.create_all` (idempotent for *table existence*, but does **not** add new columns to existing tables). Alembic is never invoked at startup.

**Implication:** If a user upgrades from v0.9.0 → v0.9.1 and the new model has a column (e.g., `error_summary` on `job_runs` from migration 0007), their existing database will not have the column. The 0007 migration is conditional on the table existing, but it will only run if someone manually runs `alembic upgrade head`. The code in `jobs.py:21-28` and `scheduler.py:25-27` then tries to write `error_summary` and the insert fails with `OperationalError: no such column`.

**Fix:** Add `from alembic import command; command.upgrade("head")` (or async equivalent) to `init_db` after `create_all`, or block startup if the schema is behind.

**Closes:** H5 in `findings.md`. **See PR 7 in `pr-roadmap.md`.**

### HUB-DB2. Migration 0007 fix for "old DBs" — present but conditional

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\migrations\versions\0007_add_job_run_error_summary.py:18-25`

```python
def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "job_runs" not in inspector.get_table_names():
        return  # fresh install — create_all will add the column
    existing_cols = {c["name"] for c in inspector.get_columns("job_runs")}
    if "error_summary" not in existing_cols:
        op.add_column("job_runs", sa.Column("error_summary", sa.Text(), nullable=True))
```

The fix is correct: on a fresh install (no `job_runs` table), the migration bails out and lets `create_all` create the column. On an existing DB, it adds the column. But this only works if Alembic is actually run (see HUB-DB1). Without that, the bug is masked until a job fails — then everything blows up.

### HUB-DB3. Migration 0004 is missing the same `if "agents" in get_table_names()` guard for *downgrade*

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\migrations\versions\0004_add_agent_table.py:19-32, 36-40`

```python
def upgrade() -> None:
    ...
    if "agents" not in inspector.get_table_names():
        op.create_table(...)
        op.create_index(...)
def downgrade() -> None:
    ...
    if "agents" in inspector.get_table_names():
        op.drop_index(...)
        op.drop_table("agents")
```

Asymmetric: `upgrade` creates the table only if missing; `downgrade` drops it only if present. That's actually correct. But the `upgrade` does **not** add a server_default for `pilot` or `created_at`/`updated`, meaning a fresh install will succeed but an upgrade (impossible today because of the guard) would have failed. Low priority.

### HUB-DB4. `JobRun.error_summary` is `Text` with no `length=` cap

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\migrations\versions\0007_add_job_run_error_summary.py:25` and `db/models.py:313`

The runtime sanitizer caps at 500 chars (`scheduler.py:26`), so this is a defense-in-depth opportunity to encode that in the schema with `String(500)` or `Text(length=500)`.

### HUB-DB5. Missing indexes for common query patterns

- `Message.session_id` is queried by the chat endpoint (`agent_chat.py:64-83`) but only has a single-column index from migration 0003 (`ix_messages_session_id`). A composite `(project_id, session_id)` would be faster and matches the other patterns in the model.
- `AgentOutput` is filtered by `(project_id, agent)` and ordered by `timestamp` — composite `(project_id, agent, timestamp)` would let MySQL/PG skip a sort.
- `EventLog` is filtered by `(project_id, agent, event_type, timestamp DESC)` for the timeline endpoint (`agents.py:288-301`) — the existing `ix_event_logs_project_ts` doesn't help.
- `JobRun` filtered by `(job_id, fired_at DESC)` — there is `ix_job_runs_job_fired` (good) but `error_summary` has no index for forensic queries.

### HUB-DB6. `ApiKey` has no index on `project_id`

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\db\models.py:70-81`

Lookups are by primary key (`id == api_key`), so this is fine. Listing keys per project would need an index — but no endpoint does that yet. No issue.

### HUB-DB7. Foreign key cascade on `JobRun.job_id` is set, but `ApiKey` has no cascade on `project_id`

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\db\models.py:74`

`ApiKey.project_id` is `ForeignKey("projects.id")` with no `ondelete`. Deleting a `Project` row will fail with `IntegrityError` (good) — but the UI has no "delete project" flow, so this is theoretical.

---

## MCP server concerns

### HUB-MC1. MCP server is project-scoped only by env var — no per-call project selection

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\mcp_server.py:39-73`

```python
def _hub_request(method, path, body=None, params=None):
    base_url = os.environ.get("HUB_URL", "http://localhost:8000")
    api_key = os.environ.get("HUB_API_KEY", "")
    project_id = os.environ.get("HUB_PROJECT_ID", "proj-default")
    ...
```

The MCP server is intended to be deployed per-project (one MCP process per Hub project). The credentials are read once from env. **If a single MCP server instance is started with the wrong env, it will silently read/write the wrong project's data.** There is no per-tool `project_id` argument and no sanity check.

**Fix:** Make `project_id` a tool parameter, or at minimum log the project name on startup and refuse to run if `HUB_PROJECT_ID` is unset.

### HUB-MC2. All MCP tools are `def`, not `async def` — event loop blocking

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\mcp_server.py` (entire file)

Discussed under HUB-CO1 / HUB-CO2. All 20+ tools are sync, and they all call `_hub_request` (sync urllib). Long-running ones (e.g., `register_agent` which writes a config dict and reads role files) will block the MCP server's event loop.

**Closes:** M2 in `findings.md`.

### HUB-MC3. `get_context` / `get_agent_context` return role guide content unbounded

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\mcp_server.py:538-569` calling `agents.py:875-917`

A Claude session calling `get_agent_context("claude")` will receive the entire role guide plus project instructions as a single tool response. For an MCP protocol with token limits, this can blow the LLM context. Should support `?max_tokens=N` or return the first chunk.

### HUB-MC4. `mark_read` accepts a `message_id` from a different project — wait, the Hub validates

Confirmed: the Hub does check `msg.project_id != project_id` (`messages.py:91`). The MCP tool relies on the Hub's 404 to surface the error. Good. (Documented for completeness.)

### HUB-MC5. `mcp_server.py` `urllib.request.urlopen` default timeout is unlimited

A misbehaving Hub will hang the MCP server forever. Set `timeout=10` on the `Request`.

**Closes:** M23 in `findings.md`.

### HUB-MC6. `register_session` has no configured-agent collision check

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\mcp_server.py:371-396` → Hub endpoint `agents.py:1100-1145`

The Hub's `register_session` (line 1100) does **not** check `if name in session_agents` like `register_agent` does. An agent can claim the principal's name. This is HUB-AP10 again, repeated because it crosses the MCP boundary.

**Closes:** M16 in `findings.md`.

### HUB-MC7. `update_task` ignores its `agent` parameter

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\mcp_server.py:244-264`

```python
def update_task(task_id: str, status: str, agent: str = "") -> Dict[str, Any]:
    ...
    return _hub_request("PATCH", f"/tasks/{task_id}", {"status": status})
```

The `agent` arg is documented as "for logging" but is **never sent to the Hub** and never used. Dead parameter — remove it or actually pass it (`{"status": status, "agent": agent}`).

**Closes:** M17 in `findings.md`.

---

## Test gaps

### HUB-TS1. No cross-project isolation / BOLA tests

**Dir:** `C:\Users\huida\Documents\projects\AgentWeave\hub\tests\`

The conftest creates a single project and a single API key. There is **no test that creates a second `ApiKey` for a different `Project` and confirms that the first key cannot read the second project's messages, tasks, logs, etc.** This is the most important class of bug for a multi-tenant system and there is zero coverage. The implementation appears correct (every query has `project_id` in the WHERE), but it has never been tested.

**Closes:** T5 in `findings.md`. **See PR 6 / T5 in `pr-roadmap.md`.**

### HUB-TS2. No tests for the auth bypass risks found in this audit

- No test for the SPA-fallback API key leak (HUB-C1).
- No test for path traversal in `get_role_context` (HUB-C2).
- No test for the `?token=` query-string auth (HUB-C3).
- No test for `id`/`timestamp` mass assignment (HUB-C4).
- No test for body-size or `content` length DoS (HUB-C5).

### HUB-TS3. No tests for `MessageCreate` / `TaskCreate` / `JobCreate` schema validation

The validators (`validate_type`, `validate_status`, `validate_priority`, `validate_session_mode`) are unreferenced by any test. They probably work, but if a Pydantic v3 upgrade renames `field_validator` they will silently break.

### HUB-TS4. No tests for the scheduler error-summary path (DB-1)

The `error_summary` column is the subject of the changelog bug. There is a `test_manual_job_run_failure_is_persisted` (`test_runtime_diagnostics.py:75-99`) but it only checks the in-memory scheduler, not what happens when the column is missing. Add a test that drops the column and confirms the right code path is taken.

### HUB-TS5. No tests for SSE multi-subscriber / cross-project isolation

**File:** `C:\Users\huida\Documents\projects\AgentWeave\hub\tests\test_sse.py:24` (only 24 lines total)

The SSE tests cover a single subscriber / single project. There is no test for:
- Two subscribers to the same project both receiving a broadcast
- A subscriber to project A **not** receiving a broadcast to project B
- Queue overflow dropping events
- `unsubscribe` correctness when the subscriber drops mid-broadcast

### HUB-TS6. No tests for the `mcp_server.py` file

**Dir:** `C:\Users\huida\Documents\projects\AgentWeave\hub\tests\` — no `test_mcp*.py` at all.

The 20+ MCP tools, including the `urllib`-based `_hub_request` and the `get_inbox` N+1 pattern, have **zero test coverage**. (Confirmed via the directory listing above.)

**Closes:** T3 in `findings.md`.

### HUB-TS7. No tests for migrations

`alembic upgrade head` and `alembic downgrade -1` are not exercised by any test. The conditional logic in migrations 0002/0003/0004/0005/0006/0007 is non-trivial and one mismatch (e.g., the `0`-quoted boolean in 0005) would not be caught.

### HUB-TS8. `test_auth.py` is too thin

Only 3 tests, all hitting `/api/v1/status`. No tests for:
- Revoked keys returning 401
- Empty `Authorization` header
- Malformed `aw_live_` keys (e.g., `aw_live_` with nothing after)
- `?token=` query-string path
- The `get_project` function's return type and project_name lookup

### HUB-TS9. No tests for the `serve_spa` API-key injection

The CRITICAL HUB-C1 bug is not covered. A 5-line regression test (`await app.get("/"); assert "aw_live_" not in resp.text`) would have caught it.

**Closed by PR 1 — see `pr1-spa-key-leak.md`.**

---

## Quick wins (low-effort, high-value)

1. **Fix HUB-C1 (SPA key leak):** Move the `<script>__AW_CONFIG__</script>` injection behind a `/api/v1/setup/token` fetch. → **PR 1**
2. **Fix HUB-C2 (path traversal):** One-line guard in `_load_role_content`. → **PR 5**
3. **Fix HUB-C3 (token in URL):** Remove the `Query(None)` `token` parameter from `get_project`. → **PR 6**
4. **Fix HUB-C4 (mass assignment):** Remove `id` and `timestamp` from `MessageCreate`, `id` and `created_at` from `TaskCreate`, `id` from `JobCreate`. → **PR 5**
5. **Fix HUB-AP1 (limit):** `limit: int = Query(50, ge=1, le=500)`. → **PR 5**
6. **Fix HUB-C5 (length):** `max_length=64` on every event_type/agent, `max_length=10000` on content, `max_length=256` on subjects, `max_length=128` on names. → **PR 5**
7. **Fix HUB-DB1 (alembic not run):** Add `command.upgrade("head")` call in `init_db` after `create_all`. → **PR 7**
8. **Add input validators** to `LogEventCreate`. → **PR 5**
9. **Reject `work_dir`** containing `..`, `~`, or non-printable chars. → **PR 5**
10. **Add a single multi-tenant test** (HUB-TS1). → **PR 6 / PR 12**
11. **Add `urllib.request.urlopen` timeout** in `mcp_server._hub_request`. → **PR 2 / M23**
12. **Remove the `agent` parameter** from `mcp_server.update_task` (HUB-MC7). → **PR 6**
13. **Add `await asyncio.gather` to `list_agents` heartbeat/message/task/context queries** to eliminate the per-agent N+1. → **PR 6**
14. **Move `_record_job_run_failure` commit outside the caller's session**. → **PR 12**
15. **Add a request-size limit middleware** (e.g., `starlette.middleware.base.BaseHTTPMiddleware` with body-length check). → **PR 6**

---

## Summary

| Severity | Count |
|---|---|
| CRITICAL security | 5 (C1 is the only one in `findings.md` as "C1"; the others are S1, S3, S5, S6, S12) |
| Concurrency | 6 |
| API bugs | 13 |
| Database / migration | 7 |
| MCP server | 7 |
| Test gaps | 9 |
| Quick wins | 15 |

HUB-C1 is the only CRITICAL issue. HUB-C2, HUB-C3, HUB-C4, HUB-C5 (S1, S3, S5, S6, S12 in `findings.md`) are HIGH security. HUB-DB1 (H5 in `findings.md`) is HIGH data-loss because users with an older Hub will see `OperationalError` on first job failure.
