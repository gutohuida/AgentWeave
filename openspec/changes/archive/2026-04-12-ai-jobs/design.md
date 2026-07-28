## Context

AgentWeave currently supports two interaction modes: human-initiated (via Hub UI or CLI) and agent-initiated (via MCP tools). Neither supports scheduled, autonomous agent activation. The agent trigger mechanism (`POST /api/v1/agent/trigger`) already exists and delivers messages to agents — AI Jobs wraps it with a scheduling layer.

The system has a Watchdog process that polls continuously in the background and a Hub (Docker) that runs FastAPI. Both are natural hosts for a scheduler. The CLI enforces zero runtime dependencies for core modules, but `jobs.py` and `mcp/server.py` can declare optional extras.

## Goals / Non-Goals

**Goals:**
- Schedule recurring messages to any agent using standard cron expressions
- Work without Hub (file-based jobs, Watchdog fires them)
- Work with Hub (DB-backed jobs, APScheduler fires them, UI manages them)
- Sync job definitions from local storage to Hub when Hub becomes available
- Agents can self-schedule or schedule peers via MCP tools
- Track run history per job (last N runs with status and session ID)
- Per-job session mode: start fresh (`new`) or resume last session (`resume`)

**Non-Goals:**
- Merging run history between local and Hub environments
- Sub-minute scheduling granularity
- Job chaining or dependencies between jobs
- Distributed locking for multi-watchdog setups
- Job output capture (agent output already flows through Hub/local logs)

## Decisions

### D1: croniter for cron parsing (both CLI and Hub)

**Decision**: Use `croniter` in both environments.

**Rationale**: croniter is a pure-Python, zero-native-extension library with a long maintenance history. It handles the full cron spec including ranges, lists, and step values. A hand-rolled parser would cover 90% of cases but break on edge cases users will inevitably hit.

**Alternative considered**: Write a minimal pure-Python parser (~100 lines). Rejected because the CLI's zero-dep constraint applies to *runtime* dependencies for the core CLI package — `croniter` can be an optional extra (`pip install agentweave-ai[jobs]`) and a hard dep for Hub.

### D2: APScheduler for Hub-side scheduling

**Decision**: Use `apscheduler>=3.x` with `AsyncIOScheduler` inside the FastAPI lifespan.

**Rationale**: APScheduler integrates naturally with asyncio, has a SQLAlchemy jobstore for persistence across restarts, and handles missed-fire policies. It fires jobs as internal function calls rather than subprocesses, keeping latency low.

**Alternative considered**: A background asyncio task with `asyncio.sleep`. Simpler but doesn't handle missed fires on restart, has no jobstore, and requires manual cron evaluation.

### D3: Watchdog as scheduler for local/git mode

**Decision**: Add `check_jobs()` to the Watchdog polling loop.

**Rationale**: Watchdog is already the persistent background process for local/git mode. It polls on a configurable interval. Adding job checking there avoids a new process and reuses the existing agent execution path (`agentweave run [agent]`).

**Constraint**: Watchdog must be running for jobs to fire in local/git mode. This is documented — not a defect.

**Alternative considered**: A separate `agentweave jobs daemon` process. Rejected as redundant with Watchdog.

### D4: File layout for local job storage

```
.agentweave/
  jobs/
    <job-id>.json          # job definition
    history/
      <job-id>/
        <iso-timestamp>.json   # one file per run
```

**Rationale**: Consistent with how tasks and messages are stored. Locking via `with lock("jobs")` for writes. History as individual timestamped files avoids append-race conditions.

### D5: Sync is definition-only, one-directional (local → Hub)

**Decision**: On transport switch to HTTP, push local job definitions to Hub (by ID, skip if exists). History stays local.

**Rationale**: History is environment-specific (local runs are different from Hub runs). Two-way sync adds conflict resolution complexity with no clear user benefit. Jobs created in Hub stay in Hub; jobs created locally can optionally promote to Hub.

### D6: Session mode per job

**Decision**: Each job stores `session_mode: "new" | "resume"`. Resume re-uses the `session_id` from the last successful run stored in the job definition.

**Rationale**: Status-check jobs benefit from continuity (agent remembers prior state). Task-execution jobs benefit from a clean slate. The agent trigger endpoint already supports both modes.

## Risks / Trade-offs

- **Watchdog not running (local mode)** → Jobs silently don't fire. Mitigation: `agentweave jobs list` shows `last_run` and a warning if overdue; documentation is explicit.
- **APScheduler missed fire on Hub restart** → APScheduler's `misfire_grace_time` and `coalesce` settings handle this; one execution fires on restart if missed.
- **Cron expression errors** → croniter raises `CroniterBadCronError` on invalid input; validated at creation time with a clear error message.
- **Concurrent Watchdog instances** → Double-firing risk if multiple watchdogs run. Mitigation: `with lock("jobs-<job-id>")` before firing; lock held for 60 seconds (cron minimum granularity).
- **Hub and local jobs diverge** → A job could exist in both places (different IDs). Mitigation: sync uses the job's `id` field as the deduplication key, not name.

## Migration Plan

1. Add `croniter` to `pyproject.toml` as optional extra (`[jobs]`) and as Hub requirement
2. Add `apscheduler` to Hub `requirements.txt`
3. DB migration: `AIJob` and `JobRun` tables added; no existing table changes
4. Watchdog extended: existing behavior unchanged, `check_jobs()` is additive
5. No breaking changes to existing CLI commands or MCP tools
6. Rollback: remove scheduler from Hub lifespan, remove `check_jobs()` from Watchdog; job files in `.agentweave/jobs/` remain inert

## Open Questions

- Should the Hub UI show jobs from all agents or only the current session's agents?
- Max history entries per job: keep last 100 runs, or configurable?
- Should `agentweave jobs run <id>` be available without Watchdog (direct execution)?
