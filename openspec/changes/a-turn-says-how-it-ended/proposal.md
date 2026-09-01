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

### Round 2, 2026-09-01: what an independent re-derivation changed

Round 2 read the code fresh against this proposal rather than re-reading round 1. The central
argument **survives**: `runStatusByRunId` is last-wins over a newest-first array, the oldest event
wins, the oldest is always `run_started`, and `TERMINAL_LABEL['started']` is `undefined`. So do the
no-migration claim (no bulk `delete(Run)` exists anywhere, and `scheduler.py:940` is
`_discard_unused_run(session, run: JobRun)`), D4's "`runDurationsByRunId` is currently correct", the
11-test-file blast radius, and every backend line citation. Four things did not survive; the two
that matter to a reader of this proposal are:

- **The third consequence is not reload-only, and the proposal said it was.** See the corrected
  paragraph below. `anotherRunIsUnderway` is OR'd into the gate, so it overrides the working
  signal in *every* state — the live path included. The change's own verification task was scoped
  to the reload case and would have passed while the live regression stood.
- **The `runs` query needs a stated coverage bound, and had none.** Design D3 argued only that the
  map may describe *more* runs than the events name, and the spec states that. Nobody argued the
  other direction: task 1.4 asked for "its own limit" without naming it, and any limit below the
  event limit silently omits older runs — which the spec's *An unknown run degrades rather than
  fails* scenario then blesses as "presents that run exactly as it presents a run with no outcome
  yet". That is the F190 symptom, re-shipped through the fix for it. Now design D7.

The other two — `AgentOutputPanel` being the component that must carry the run facts, against a
design risk line saying it was not expected to need them, and four stale UI line numbers — are in
`design.md` under *Round 2 corrections, 2026-09-01*.

One alarm was raised and killed rather than filed. `grep -E 'Run\.status == "[a-z_]+"'` reports
`in_progress`, which would break D5's enumeration — but `Run\.status` matches inside
`JobRun.status`, and the scheduler's `skipped`/`in_progress` writes are all under `run = JobRun(`.
`Run.status` really is `{running, completed, failed, stopped, interrupted}`. D5 stands.

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

**Third consequence, repaired as a side effect — corrected in round 2.** `AgentTimeline.tsx:114`
decides a run has settled from two signals: the streamed status entry, and the timeline status as a
backstop "for history loaded fresh". The backstop is dead because every run reads `started`, and the
streamed entry is dead after a reload because it is never persisted.

Round 1 stopped there and concluded the failure was a reloaded conversation's, where "both fail
together". **It is not scoped to reload.** The gate is

```
runVisiblyActive = isRunning && (!lastRunSettled || anotherRunIsUnderway)
```

and `anotherRunIsUnderway` (`:131`) is true whenever the event window holds **two or more runs**,
because every run reads `started` and `started` is not in `TERMINAL_STATUSES`. It is OR'd, so it
overrides `lastRunSettled` whatever that says — including the live path, where the streamed status
entry is present and working. `runVisiblyActive` therefore reduces to exactly `isRunning`, the
polled roster field, which is the pre-fix behaviour the 2026-08-18 change was written to replace.

So the defeat is unconditional for any agent with two or more runs in its window: the tail fix
(operator, 2026-08-18: *"It still linger a little bit"*) is defeated live and not merely on reload,
and the stop-then-send fix (operator, 2026-08-20) is satisfied only vacuously — the indicator shows
because it always shows, not because a second run is underway. A single-run conversation is
unaffected, which is why this survived every manual look.

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
