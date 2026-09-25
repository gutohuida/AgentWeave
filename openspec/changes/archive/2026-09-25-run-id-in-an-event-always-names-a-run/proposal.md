# Proposal — `run_id` in an event always names a run

**Round 1, 2026-09-24** (bundle B2, spec track S7 after decision D1, second half). Finding:
**F149 (C)**, re-verified against HEAD `ce086b6`: every site it cites still publishes a `JobRun` id
under the bare key `run_id`, at moved line numbers. **Nothing here is implemented yet.**

## Why

Every event on the project stream uses `run_id` to mean a `Run` (`run_started`, `run_completed`,
`run_failed`, `run_stopped`, `run_interrupted`, the queue events, permission requests). Three job
events use the same key for a **`JobRun`** id, and both id spaces mint `run-{short_id()}`
(`scheduler.py:3062`, `:3716`; `api/v1/jobs.py:74`), so nothing in the value tells them apart:

| Event | Sites (HEAD) | Persisted? |
|---|---|---|
| `job_fired` | `scheduler.py:3480-3491` (SSE), `:3493-3505` (log), `:3774-3790` (extra selection, both) | yes |
| `job_run_skipped` | `scheduler.py:3084-3097`, `:3126-3139`, `:3161-3174`, `:3310-3323` | yes |
| `job_run_failed` | `scheduler.py:3520-3535`; `api/v1/jobs.py:87-100` | yes |

`POST /jobs/{id}/run` answers the same id as `run_id` too (`api/v1/jobs.py:1510`), and the MCP tool
`run_job` hands that body to an agent (`mcp_server.py:929-937`).

F149 said the cost was confined to reading the activity log. R1 found **one code reader it misleads**:
`GET /agents/{name}/timeline` (`api/v1/agents.py:795`) collects `run_id` from every event it returns and looks each up in
`runs` to build the run facts map (`api/v1/agents.py:883-891`). A `job_fired` carrying a `JobRun` id
is looked up as a run and silently misses. Harmless today; it is exactly the confusion the finding
predicted, in code rather than in a reader's head.

Decision D1 (recommended, `spec-queue/tracks/B2.md`): the key is renamed, outright.

## What Changes

- The three job events carry the `JobRun` id as **`job_run_id`**, and no longer carry `run_id`, in
  both the SSE broadcast and the persisted payload (the ten sites above).
- `POST /jobs/{id}/run` answers `{"success": true, "job_id": …, "job_run_id": …}`. The UI's type
  (`hub/ui/src/api/jobs.ts:252`) follows; nothing in the UI reads the value.
- **No dual-emission period and no rewrite of stored events.** Persisted rows written before this
  keep `run_id`. No reader depends on the key: `useSSE.ts:524-535` reads only `id`; `eventSummary.ts:
  57-65` reads `job_name`, `job_id`, `agent`, `error_summary`, `reason`; `agents.py:884` already
  tolerates an id that names no run.
- A requirement in `agent-stream-events` states the rule for every event, so the next event with a
  second kind of id does not reuse `run_id`.

## Capabilities

### Modified Capabilities

- `agent-stream-events`: adds *An event's `run_id` names a run*.

## Impact

- `hub/hub/scheduler.py`, `hub/hub/api/v1/jobs.py`, `hub/ui/src/api/jobs.ts` (type only; a UI bundle
  refresh is still needed if the type change alters the build output, which a type-only edit does
  not).
- Routes changed: `POST /jobs/{id}/run` (response key). What it returns when the scheduler raises is
  unchanged: `_record_job_run_failure` then 500 (`api/v1/jobs.py:1499-1506`); that path's event key is
  renamed with the rest.
- Collides on file with `pressing-run-names-the-reason-that-held` (open; edits `run_job`'s
  `if not success` branch, `api/v1/jobs.py:1419-1497`). This change touches only the success return
  at `:1510` and `_record_job_run_failure`'s payload. Land either first; the second rebases.
