## Why

A turn that was stopped, failed or interrupted tells the operator nothing: the conversation shows
the work, then stops, and the agent chip returns to `idle`. A turn killed mid-sentence is
indistinguishable from a turn that simply had nothing to say. The feature to say otherwise exists and
ships — `AgentTimeline.tsx:56-60` defines `TERMINAL_LABEL` for `failed`, `stopped` and `interrupted`,
and the strings are in the served bundle — but it can never fire.

The cause is a round trip that loses information it started with. At
`hub/hub/api/v1/agent_trigger.py:2001-2006` the outcome and the event name are decided on one line
(`final_status, lifecycle_event = "stopped", "run_stopped"`). The status is written to
`Run.status` (`hub/hub/db/models.py:1110`, indexed) and the event name is persisted to `EventLog`.
The timeline route never reads `Run`, so the browser decodes the status back out of the event *name*
via `LIFECYCLE_EVENT_STATUS` (`hub/ui/src/lib/agentTimelineModel.ts:112-118`) — a map that is the
server's own assignment run backwards. That decode is a last-wins loop (`:187-199`) over an array the
route deliberately sorts newest-first (`hub/hub/api/v1/agents.py:800`, `reverse=True` then `[:50]`),
so the *oldest* event wins for every run. The oldest is always `run_started`, and
`TERMINAL_LABEL['started']` is `undefined`.

Measured across six real runs: six `started`, of which three were stopped and two completed.

This is filed as **F190 (severity A)** in `scripts/drive/FINDINGS.md`.

## What Changes

- **BREAKING** `GET /api/v1/projects/{project_id}/agents/{name}/timeline` returns an envelope
  `{ events, runs }` instead of a bare `AgentTimelineEvent[]`. `runs` is a map keyed by `run_id`
  carrying each run's own facts — `status`, `exit_code`, `started_at`, `ended_at` — read from the
  `Run` table.
- The route gains a fourth concurrent query alongside the three it already runs
  (`hub/hub/api/v1/agents.py:737-763`), filtered by `project_id` and `agent` on the existing
  `Index("ix_runs_project_agent", ...)` (`hub/hub/db/models.py:1152`).
- **`runStatusByRunId` is deleted** (`hub/ui/src/lib/agentTimelineModel.ts:187-199`). The client
  stops decoding a status out of an event name and reads the one the server already decided.
- **`runDurationsByRunId` is deleted** (`:138-168`). `Run.started_at` and `Run.ended_at` carry the
  same fact the function reconstructed from event timestamps.
- The terminal status line is **persisted as an `AgentOutput` row**, not only broadcast
  (`agent_trigger.py:2129-2142` and `:2723-2736`). Today `/agents/{name}/output` for a stopped run
  holds one `kind="thinking"` row and no status row at all, so the exit code is unrecoverable after
  a reload.
- A new requirement states that a model function consuming an API payload is tested against a
  fixture derived from that route's **actual** ordering. `agentTimelineModel.test.ts:223-235` is
  green today because it feeds the opposite ordering to the one the route produces.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-stream-events`: adds requirements for a run's terminal outcome being visible and durable,
  for the timeline carrying a run's own facts rather than an encoding of them, and for payload-shaped
  model functions being tested against real route ordering. Its 19 existing requirements cover the
  event envelope, the kind taxonomy, run identity and turn rendering; none of them says a run's
  outcome must be shown, which is why this shipped and rotted without a test failing.

## Impact

**Affected APIs**

- `GET /projects/{project_id}/agents/{name}/timeline` — response shape changes. One hook consumes it,
  `useAgentTimeline` (`hub/ui/src/api/agents.ts:387-392`).

**Affected code**

- `hub/hub/api/v1/agents.py` — the timeline route.
- `hub/hub/schemas/agents.py` — a new envelope schema beside `AgentTimelineEvent`.
- `hub/hub/api/v1/agent_trigger.py` — persist the status row on both the exec and app-server paths.
- `hub/ui/src/lib/agentTimelineModel.ts` — two functions removed.
- `hub/ui/src/components/agents/AgentTimeline.tsx` — reads the map instead of computing it; the
  three consumers are the terminal label (`:202`), `lastRunSettled` (`:116`) and
  `anotherRunIsUnderway` (`:133`).
- `hub/ui/src/components/agents/AgentActivityTab.tsx`, `AgentOutputPanel.tsx` — consume the timeline
  shape.
- **11 UI test files** mock the timeline response and must move to the envelope: `agentHandoff`,
  `agentRunningComposer`, `batchedQuestionComposer`, `composerPermissionDefault`,
  `continueStartsWhatItNames`, `conversationControls`, `conversationDestination`, `handoffPlacement`,
  `specChatSurface`, `workingIndicator`, `agentTimelineModel`. This is the largest mechanical cost of
  the change and is the reason to plan it rather than discover it.

**No migration.** `Run` rows are never deleted — the only `session.delete(run)` in the Hub is a
`JobRun` (`hub/hub/scheduler.py:940`), and `_prune_job_history` prunes `JobRun`. Every historical
run's status is already recorded, so existing conversations begin rendering correctly on first read.

**Third consequence, repaired as a side effect.** `AgentTimeline.tsx:114-116` decides a run has
settled from two signals: the streamed status entry, and the timeline status as a backstop "for
history loaded fresh". The backstop is dead because every run reads `started`, and the streamed
entry is dead because it is never persisted — so on a reloaded conversation both fail together, and
`anotherRunIsUnderway` counts every older run as still underway. That defeats the exclusion written
specifically to stop the working indicator lingering under a finished answer (operator, 2026-08-18:
*"It still linger a little bit"*).

## Non-Goals

- **Not sweeping for other order-sensitive reducers.** The new testing requirement is stated here
  because this change is its best evidence, but the sweep it implies — every React Query result used
  without its `error`, every `model_validator` racing a state machine, every reducer over a payload
  whose ordering is implicit — is separate work and is recorded as D-4 in `spec-queue/DECISIONS.md`.
- **Not changing the route's sort order.** `reverse=True` then `[:50]` is correct: it means "the 50
  most recent events". Reversing it would return the oldest 50.
- **Not narrowing the `runs` map to the run ids the returned events mention.** The fourth query runs
  concurrently with the other three and therefore cannot know them; discovering them first would
  serialise the `asyncio.gather` to save a few hundred bytes. The over-fetch is deliberate and is
  stated so nobody "optimises" it later.
- **Not adding a `/runs` API.** No such route exists today and none is introduced; the run facts are
  carried by the timeline that describes them.
- **Not reconciling `Run.status` with `JobRun.status`.** They are different tables with different
  domains; `skipped` and `in_progress` belong to `JobRun` and are out of scope.
