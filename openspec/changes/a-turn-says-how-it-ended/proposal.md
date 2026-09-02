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

### Round 3, 2026-09-01: what a second independent re-derivation changed

Round 3 read the model, the component, the route, the `Run` table and both terminal paths before
reading either earlier round's reasoning. The central argument survives a second time, as does
round 2's correction that `anotherRunIsUnderway` defeats the working indicator live and not only on
reload. Two things did not survive, and both are cases of a *right* observation reaching a
mechanism that cannot deliver it:

- **Round 2 bounded the run query's size when the problem was its ordering.** Its arithmetic — up to
  50 distinct runs can be named, so the run limit must be at least 50 — is correct and is not the
  operative constraint. A limit decides how many rows return, not which, and task 1.4 ranked them
  by `started_at`. `run_reconciliation.reconcile_interrupted_runs` sweeps every still-`running` row
  in the database at Hub start and writes its lifecycle event *then*, so one bounce makes an
  agent's newest events name its oldest runs. An implementation obeying round 2 to the letter would
  drop exactly those, satisfy D7 as written, pass the test D7 commissioned, and still show older
  turns with no outcome — F190 again, through its own fix, for the second round running. The map is
  now read by id off the events themselves, so coverage is a property of the query rather than an
  argument about limits. D3 is reversed; D7 is rewritten.
- **`Run.started_at` is not the `run_started` event's timestamp.** The row is constructed inside the
  trigger request, before workspace preparation and spawn; the event is written once the process
  exists. D4 called them "the same fact, recorded". Durations will read longer, and a run whose
  spawn failed gains one it does not have today.

Both are recorded in `design.md` under *Round 3 corrections, 2026-09-01*, along with what was
re-derived and left standing and one alarm raised and killed.

Its supplementary pass over phase 2 — which the first sitting had not read — then claimed that
`lastRunSettled`'s *other* signal has never fired either, for anyone. **Phase 0 falsified that on
2026-09-01 and round RA re-argued D6 from the measured premise on 2026-09-02** — see the corrected
paragraph under *Third consequence* below, and design D6. The pass also corrected three task-level
claims, and those three stand: `record_agent_output` cannot reproduce the
`status-{run_id}` id, task 2.2's justification cites a Handoff consumer that was deleted, and the
11-file fixture cost is concentrated in two files while the other nine would stay green un-updated.
All are in `design.md` under *Supplementary pass, 2026-09-01*.

### Phase 0 and round RA, 2026-09-01/02: the defect was watched, and one decision was re-argued

The operator approved this change on the condition that the defect be observed live before a line is
implemented. It was, on 2026-09-01 against a Hub on 8011 with a fresh fixture project
(`scripts/drive/FINDINGS.md`, *F190 phase 0*). **The headline held**: a stopped run's turn presents
no terminal label, the database says `stopped`, the route says `started`, and the label is still
absent after a reload with no `kind="status"` row for that run. So did the multi-run lingering tail,
and so did the restart-time skew between a run's lifecycle event and its `Run.started_at` that D3's
reversal rests on.

**One observation falsified a claim, which under task 0.7 stopped the change and returned it to a
round.** Round 3's supplementary pass had said `lastRunSettled`'s first signal has never fired for
anyone; the single-run indicator was watched releasing cleanly on the answer's own snapshot. Phases
1-7 were blocked in `tasks.md` until a round re-derived D6 from the true premise.

**Round RA, 2026-09-02, is that round, and it unblocked them.** Signal 1 fires — for a run that
finished, written by a second producer round 3b did not look for (`runner_parsing.py:356`). D6's
purpose survives on a narrower argument: it extends that signal to runs that did *not* complete, and
it makes the exit code durable. Two attributions it loses: D6 does not repair the working indicator
(D1-D5 do, by fixing signal 2), and it cannot reach the `interrupted` outcome at all, because
`run_reconciliation` writes an `EventLog` row and no `AgentOutput`. The round also found two
consequences of persisting an invisible row that no earlier round named — a completed run gains a
second matching entry, and a turn whose only agent output is that row loses its "Worked for Xs"
line, because `firstAgentBlockId` selects it and its fragment returns `null`. New tasks 2.1a and
4.5a, and a new scenario in *A run's terminal outcome is visible*. Everything else in the change was
re-read and left unedited; design's *Round RA* section says so explicitly rather than reporting only
what moved.


## What Changes

- **BREAKING** `GET /api/v1/projects/{project_id}/agents/{name}/timeline` returns an envelope
  `{ events, runs }` instead of a bare `AgentTimelineEvent[]`. `runs` is a map keyed by `run_id`
  carrying each run's own facts — `status`, `exit_code`, `started_at`, `ended_at` — read from the
  `Run` table.
- The route gains a fourth query after the three it already runs
  (`hub/hub/api/v1/agents.py:737-763`) — a primary-key `IN` lookup on the run ids the returned
  events name, so the map covers exactly them. **Changed in round 3**: rounds 1 and 2 specified a
  fourth *concurrent* query scoped by `project_id` and `agent`, which cannot know those ids and had
  to approximate coverage with an ordering and a limit. See design D3 and D7.
- **`runStatusByRunId` is deleted** (`hub/ui/src/lib/agentTimelineModel.ts:187-199`). The client
  stops decoding a status out of an event name and reads the one the server already decided.
- **`runDurationsByRunId` is deleted** (`:138-168`). `Run.started_at` and `Run.ended_at` carry the
  fact the function reconstructed from event timestamps — **not to the same instant**, corrected in
  round 3: the row is stamped before the spawn and the `run_started` event after it, so every
  rendered duration grows by the spawn cost. The row's figure is adopted deliberately.
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
  `useAgentTimeline` (`hub/ui/src/api/agents.ts:387-392`), but **two components call that hook
  independently** — `AgentOutputPanel.tsx:330` and `AgentActivityTab.tsx:24` — so both break on the
  envelope, not just the one that renders the run facts.

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
because it always shows, not because a second run is underway.

**Round 3's supplementary pass then said it was worse than that, and it was wrong — measured, then
re-argued.** It claimed `lastRunSettled`'s other disjunct fails too for every agent, on the grounds
that the streamed status entry is broadcast over SSE and never persisted while `entries` come only
from `useAgentChatHistory`'s invalidate-and-refetch of persisted rows. Phase 0 watched the opposite
happen: on a single-run conversation the indicator went out **on the same snapshot the answer text
landed**, 0.7 s before the roster poll — the atomic handover the gate was written to produce. The
error was an identification, not an observation. The entry that satisfies
`isSuccessCompletionEntry` is written by a second producer — the stream parser's
`status_event("completed", …)` (`runner_parsing.py:356`), persisted through `record_agent_output`
(`agent_trigger.py:1925-1938`) — not by the broadcast-only line at `agent_trigger.py:2132` that the
pass traced.

**What survives is narrower and still real.** Signal 1 fires for a run that *finished*, and only for
that. A stopped run, a failed run and an interrupted run each produce no `phase="completed"` row at
all, because the runner never emits the `result` line the parser turns into one. So for every run
that did not complete, `lastRunSettled` is false for the whole life of that conversation and the
gate collapses to `isRunning` through the left branch. Round 2's correction governs everyone else:
with two or more runs in the window, `anotherRunIsUnderway` collapses the gate whatever signal 1
says. Between them, the only case in which the indicator behaves correctly today is a single run
that completed successfully — which is exactly what phase 0 measured, and which is why this survived
every manual look. Round RA, 2026-09-02, re-derived this from the code; see design D6.

## Non-Goals

- **Not sweeping for other order-sensitive reducers.** The new testing requirement is stated here
  because this change is its best evidence, but the sweep it implies — every React Query result used
  without its `error`, every `model_validator` racing a state machine, every reducer over a payload
  whose ordering is implicit — is separate work and is recorded as D-4 in `spec-queue/DECISIONS.md`.
- **Not changing the route's sort order.** `reverse=True` then `[:50]` is correct: it means "the 50
  most recent events". Reversing it would return the oldest 50.
- **Not keeping the map wider than the events.** Rounds 1 and 2 made the opposite non-goal here,
  on the grounds that narrowing would serialise the `asyncio.gather` to save a few hundred bytes.
  Round 3 reversed it: the over-fetch was never about bytes, it was an approximation of a coverage
  property the spec states absolutely, and no ordering on `Run` tracks the recency of the events
  that name it. The map is now exactly the runs the response talks about.
- **Not adding a `/runs` API.** No such route exists today and none is introduced; the run facts are
  carried by the timeline that describes them.
- **Not reconciling `Run.status` with `JobRun.status`.** They are different tables with different
  domains; `skipped` and `in_progress` belong to `JobRun` and are out of scope.
