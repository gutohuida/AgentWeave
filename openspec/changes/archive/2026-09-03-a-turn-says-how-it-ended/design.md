## Context

`GET /projects/{project_id}/agents/{name}/timeline` (`hub/hub/api/v1/agents.py:729-801`) is a
**fan-in**: three independent queries — `Message`, `EventLog`, `AgentHeartbeat` — each with its own
`limit`, run concurrently under `asyncio.gather`, merged into one list, sorted newest-first, and
truncated to 50. Nothing in the code states a rule that only three tables may participate; what the
shape does imply is that each source produces *events*, things that happened.

`Run` is different in kind. It is not a thing that happened; it is the subject of things that
happened. That is the whole design question this change answers: whether the route stays "a list of
events" or becomes "events, and the state of the runs they describe".

Current state, measured:

- The outcome and the event name are decided on one line, `agent_trigger.py:2001-2006`.
- `Run.status` is written (`models.py:1110`, `String(32)`, indexed) and never read by this route.
- The event name is persisted to `EventLog` by `_broadcast_run_lifecycle` (`agent_trigger.py:1677`,
  "Persist + SSE-broadcast"), whose payload is `{"agent", "run_id", **fields}` — an open dict that
  already carries `exit_code`.
- The browser decodes the status back out of the event name (`agentTimelineModel.ts:112-118`) with a
  last-wins loop (`:187-199`) over the newest-first array. The oldest event wins. It is always
  `run_started`.

Six real runs measured: six `started`, three of which were stopped and two completed.

## Goals / Non-Goals

**Goals:**

- A run's outcome is presented from the fact the server recorded, not from a re-derivation of it.
- The client holds no function that turns an event array into run state.
- The exit code survives a reload.
- The repository gains a stated rule about testing payload-shaped model functions, since this defect
  passed review behind a green test.

**Non-Goals:**

- Changing the route's sort order. `reverse=True` then `[:50]` means "the 50 most recent"; reversing
  it returns the oldest 50.
- Sweeping for other order-sensitive reducers (recorded as D-4 in `spec-queue/DECISIONS.md`).
- Introducing a `/runs` API.
- Reconciling `Run.status` with `JobRun.status`.
- Backfilling anything.

## Decisions

### D1 — The route reads `Run`, rather than the event payload carrying the status

**Chosen:** a fourth concurrent query on `Run`, scoped by `project_id` and `agent`.

*Rejected: adding `status=final_status` to the `_broadcast_run_lifecycle` kwargs.* This is the
cheapest possible change — one kwarg at two call sites, no schema change, because `data` is already
`Record<string, unknown>` on the client. It was rejected because it fixes only runs that end **after**
the change: every EventLog row already written carries no status, so the client would still need the
event-name decode as a fallback for history, which means keeping the very function this change
exists to delete. Reading `Run` fixes new and old alike, because `Run` rows are never deleted — the
only `session.delete(run)` in the Hub is a `JobRun` (`scheduler.py:940`) and `_prune_job_history`
prunes `JobRun`.

*Rejected: fixing the reducer in place (make it order-independent by splitting started/terminal, as
its sibling `runDurationsByRunId` already does).* Correct, cheap, and leaves the client deriving a
value the server already computed and stored. It remains the fallback position if D2 proves too
costly.

### D2 — The response becomes an envelope, and `runs` is a keyed map

**Chosen:** `{ events: [...], runs: { "<run_id>": { status, exit_code, started_at, ended_at } } }`.

*Rejected: stamping the run's status onto each lifecycle event's `data` and keeping the response an
array.* Non-breaking, and it neutralises the ordering hazard because every event for a run would
carry the same authoritative value — but the reducer survives, still looks order-dependent to the
next reader, and a future event type could reintroduce the bug. The hazard would be masked, not
removed.

*Rejected: `runs` as a list.* Ordered, conventional, paginates naturally — and it forces the client
to build the index itself (`Object.fromEntries(...)`). That is order-independent and harmless, but it
is a client-side reduction over run state, which is the exact shape being deleted. The next reader
could not distinguish a harmless `keyBy` from the reducer that broke.

The keyed map is chosen because **every consumer is a lookup or an unordered scan** — the terminal
label (`AgentTimeline.tsx:220`), `lastRunSettled` (`:114`), `anotherRunIsUnderway` (`:131`) and the
duration lookup. No consumer needs ordering. Precedent exists: `hub/hub/schemas/jobs.py:125`,
`queue: Dict[str, int]`.

### D3 — The `runs` map is looked up by the run ids the returned events name

**Superseded in round 3.** Rounds 1 and 2 chose a fourth query inside the existing
`asyncio.gather`, scoped by `project_id` and `agent`. That is reversed here, and D7 records why the
decision was reopened rather than merely tightened.

**Chosen:** the three existing queries run concurrently as they do today; the merged, truncated
event list is then scanned for `data.run_id`, and a second query reads exactly those rows —
`select(Run).where(Run.project_id == project_id, Run.id.in_(run_ids))`, a primary-key lookup with
no limit and no ordering. An empty id set skips the query entirely.

The `project_id` predicate is deliberate and was added in round 3's final read, which caught this
decision's own first draft dropping it. The ids do come from rows the route already filtered, so
the query is safe by inference either way — but the `runs` map is a new cross-project leak surface,
`test_bola.py`'s isolation test covers this route precisely because that matters, and
`ix_runs_project_agent` makes the predicate free. Enforce it rather than infer it.

*Rejected: a fourth concurrent query scoped by `project_id` and `agent`, ordered and limited.* This
was the round 1/round 2 choice, and it saves one sequential database round trip. It was reversed
because the round trip is not what it costs. A query that cannot know the run ids must approximate
coverage with an ordering and a limit, and **no ordering available on `Run` tracks the recency of
the events** — see D7. Buying one round trip with an approximation of a property the spec states
absolutely is the wrong trade, and it was only ever made when the currency was "a few hundred
bytes" rather than correctness.

*Rejected: keeping the concurrent query and ordering it by `COALESCE(ended_at, started_at)`
instead.* This is closer — that expression tracks the run's own latest lifecycle moment, so it
mostly ranks runs the way `EventLog` does. But "mostly" is the whole objection: it is still a
heuristic standing in for a set the route can compute exactly, and it would need its own boundary
argument, its own test, and its own paragraph explaining when it is allowed to be wrong.

The consequence for the response shape is that the map no longer describes runs the events do not
name. That is a simplification of the contract, not a loss: nothing consumed the surplus.
### D4 — Both reducers go, not one

`runDurationsByRunId` (`:138-168`) is currently **correct** — it splits `run_started` from terminal
events into two maps and combines at the end, so ordering cannot hurt it. Retiring it is cleanup,
not repair, and it is included deliberately: leaving one function that still derives run facts from
the event array, immediately beside the one just deleted, is the half-migration that produced this
adjacency in the first place. `Run.started_at` and `Run.ended_at` are the same fact, recorded.

The negative-duration guard that function carries (a clock that went backwards yielding
"Worked for -3s") must be preserved at the new call site; the concern does not disappear with the
function.


**The two timestamps are not the same instant, and round 3 corrects "the same fact, recorded" to
say so.** `Run.started_at` defaults at row construction (`agent_trigger.py:1073`), inside the
trigger request, before workspace preparation and before anything is spawned. The `run_started`
`EventLog` row is written only once the pty exists (`:1857-1864`). Substituting the row for the
events therefore makes every rendered duration *longer* by whatever spawn cost — the figure starts
measuring from when the operator's turn began rather than from when the process did.

That is arguably the more honest number and it is the one this change adopts, but it is a visible
behavioural change and it has to be decided rather than absorbed: a component test written against
the event-derived figure will disagree with it, and the right response is to re-baseline the test,
not to reconcile the two.

The same substitution gives a duration to a run that never spawned. `_execute_run`'s spawn-failure
branch (`:1798-1804`) sets `status`, `error` and `ended_at` but never persisted a `run_started`, so
`runDurationsByRunId` renders nothing for it today; `started_at`/`ended_at` both exist, so the
envelope will. "Worked for 0s" on a run that failed to start is acceptable and arguably correct —
it is named here so it is recognised as intended rather than filed as a regression.
### D5 — `running` maps to the client's `started`

`Run.status` is `{running, completed, failed, stopped, interrupted}`. The client's
`RunLifecycleStatus` is `{started, completed, failed, stopped, interrupted}`. One rename at the
boundary. `skipped` and `in_progress` belong to `JobRun` and never appear here.

### D6 — The terminal status row is persisted at both call sites, and it is the low-latency signal for a run that did not finish

**Re-argued in round RA, 2026-09-02, after phase 0 falsified the premise round 3b gave this
decision.** What follows is derived from the code, not from either earlier argument.

`AgentTimeline.tsx:88-111` names two settled-signals. Signal 1 is a persisted `AgentOutput` row with
`kind="status"` and `payload.phase == "completed"` — `isSuccessCompletionEntry`
(`agentTimelineModel.ts:24-28`). Signal 2 is the lifecycle event decoded by `runStatusByRunId`.

**Signal 1 fires today, and it fires for exactly one class of run *on one of the two wired
runners*.** The row that satisfies it is written by the stream parser, not by the finalize block:
`runner_parsing.py:346-356` turns Claude's `result` message into
`status_event("completed", summary="Completed")` when `is_error` is not true, and `status_event`
(`runner_events.py:180-187`) builds `kind="status"`,
`payload={"version": …, "phase": "completed", …}` — the predicate exactly. Every parsed event is
persisted through `record_agent_output` (`agent_trigger.py:1925-1938`). So the predicate matches
whenever, and only whenever, **the Claude CLI** announced a successful turn:

| runner | how the run ended | a persisted `phase="completed"` row today? |
|---|---|---|
| claude / claude_proxy / native | completed — `result` with `is_error` false | **yes**, the parser's |
| claude / claude_proxy / native | `result` with `is_error` true | no — `error_event`, `kind="error"` (`runner_parsing.py:346-350`) |
| claude / claude_proxy / native | stopped mid-run | no — the process is killed before any `result` line |
| claude / claude_proxy / native | failed on a non-zero exit | no |
| **codex** (exec **or** app-server) | **any outcome, including a clean completion** | **no — never** |
| any | interrupted by a Hub restart | no |

**The runner column is round RB's correction and it is not a detail.** `parse_claude_line` is
selected only for `runner in ("claude", "claude_proxy", "native")` (`agent_trigger.py:1867`);
everything else falls through to `parse_codex_line`, whose only `status_event` is `"plan"`
(`runner_parsing.py:574`), and the app-server transport's only `status_event` is `"plan"` as well
(`codex_appserver.py:544`). `status_event("completed")` occurs **exactly once in the whole Hub**, in
the Claude parser. So no Codex run of either transport has ever had a persisted `phase="completed"`
row — not a stopped one, and not one that finished cleanly.

Phase 0 measured both ends of that table. A completed run's conversation holds exactly one matching
entry and the single-run indicator released on the same snapshot the answer text landed, 0.7 s
before the roster poll (task 0.3). The stopped run had no `status` row at all — three of the agent's
nine output rows were `status` and none of them was its (tasks 0.3, 0.5).

**Round 3b's error was an identification, and it inverted this decision's scope.** It read the
terminal status line at `agent_trigger.py:2131-2153`, saw correctly that it is only broadcast, and
concluded that no row of that shape is ever persisted. A different producer writes the same shape.
D6 therefore does not make signal 1 work *for the first time, for everyone* — **on a Claude
runner** it extends signal 1 from **the run that finished** to **the run that did not**.

**On a Codex runner it is the first-time repair, for every outcome including success**, which is
what rounds 1-3 claimed for all runners and round RA retracted for all runners. Round RA identified
the second producer correctly and then generalised a Claude-only producer to the whole product; the
correct statement is per-runner, and both halves of it are load-bearing. Round RB measured the UI
consequence: rendering `AgentTimeline` with a completed turn and only `run_started` in
`timelineEvents` — the pre-refetch window — the working indicator is **absent** when the Claude
parser's status row is among the entries and **present** when it is not, and codex's own
`phase="plan"` status row does not satisfy the predicate either (3 assertions, all passing, on
unmodified code). So the 2026-08-18 lingering-tail complaint is fixed for Claude and **still live
for Codex today**, on every turn including a clean one. Filed as **F270 (C)**.

**What D6 buys, argued from that premise.**

1. *A durable exit code.* Unchanged and independently true. `agent_trigger.py:2132-2142` (process
   path) and `:2721-2735` (app-server path) broadcast `{"phase": "completed", "exit_code": …}` and
   persist nothing, so once the live stream is gone the exit code is unrecoverable. Measured at
   task 0.5.
2. *Signal 1 for every run the finalize block reaches.* That broadcast sits directly inside the
   `async with async_session_factory() as db:` at `:2009` — not inside the `if run is None` guard —
   so it is reached for `stopped`, `failed`, `completed` and the binding-conflict case alike
   (`:2000-2006`). Persisting it makes `lastRunSettled` true for a stopped or failed run at the
   instant the run ends, rather than never.

**What D6 does not buy, and this is what rounds 1-3 attributed to it.** It does not repair the gate.

```
runVisiblyActive = isRunning && (!lastRunSettled || anotherRunIsUnderway)
```

collapses to `isRunning` through `anotherRunIsUnderway` whenever the event window holds two or more
runs, because signal 2 reports `started` for every run — measured live at task 0.4, on an agent that
released cleanly with one run in its window and lingered under a finished answer with two. Repairing
that is D1-D5's work. Once the `runs` map lands, signal 2 is correct and `anotherRunIsUnderway` is
correct with it.

So D6 returns to being what `AgentTimeline.tsx:108-111` always said it was — the fast signal that
closes the refetch tail, with the lifecycle event as "the backstop" — plus the correction that today
it closes that tail only for runs that finished. Without D6, after D1-D5 a stopped run's indicator
would still linger for one `useAgentTimeline` round trip: the 2026-08-18 complaint surviving in the
narrower case. That is a smaller claim than "D6 repairs the working indicator" and it is the one the
code supports.

**One outcome D6 cannot reach: `interrupted`.** `reconcile_interrupted_runs`
(`run_reconciliation.py:49-66`) sets the row's status and calls `persist_event`; it writes no
`AgentOutput` — `record_agent_output` does not appear anywhere in that module. A run interrupted by
a Hub death therefore has no status row before this change and none after it, and its turn settles
on signal 2 alone. That is correct rather than a gap — the Hub was not running to write one — but it
must not be asserted otherwise, which is why task 2.1 covers the two spawn paths and not this one.

**Two consequences of persisting an invisible row, neither previously named.**

- *A completed run on a Claude runner gains a second matching entry; a completed Codex run gains
  its first.* The parser's row (`content="Completed"`,
  `payload={"version": 1, "phase": "completed", "summary": "Completed"}`) and the finalize block's
  (`content="Run completed (exit 0)."`, `payload={"phase": "completed", "exit_code": 0}`) both
  satisfy `isSuccessCompletionEntry`, and `AgentTimeline.tsx:430` returns `null` for each, so
  nothing is drawn twice. The exit code lives only on the second. This is a duplication to state,
  not to remove: suppressing the parser's row would delete the signal that works today, and
  suppressing the finalize block's for a completed run would make the durable exit code
  outcome-dependent.
- *The invisible row can swallow the turn's stat line.* `firstAgentBlockId`
  (`AgentTimeline.tsx:384-389`) is the first block that is a work block or carries an `agent_output`
  entry. A `status` entry is neither work nor a message — `RESULT_OUTPUT_KINDS` holds `status`
  (`agentTimelineModel.ts:9`) — so it is its own `entry` block and qualifies. `durationLine` is
  rendered *inside* that block's fragment (`:406-418`), and the fragment for a success-completion
  entry is `return null` (`:430`). For a turn whose only agent output is this new row — a run
  stopped before it produced anything, or a spawn that failed — "Worked for Xs · N tokens" is
  attached to a block that renders nothing and disappears with it. This lands exactly where D4 does
  the most work: task 4.5 gives precisely those runs a duration for the first time, by taking it
  from `Run.started_at`/`ended_at`. Task 4.5a is added for it.

  **This one was measured, not read.** Round RA rendered the real `AgentTimeline` under vitest with
  two throwaway probes (run afterwards, deleted before commit — the day window does not implement).
  Probe 1, against the shipped `agentTimelineModel`: a `status` entry has `entryCategory` `result`,
  becomes its own `entry` block, and `firstAgentBlockId`'s own expression selects it when it is the
  turn's only agent output — while a `thinking` row ahead of it takes the slot instead, which is why
  nothing shows this today. Probe 2, rendering `AgentTimeline` with `run_started`/`run_stopped` five
  seconds apart: a turn holding a text row **and** the status row renders `turn-worked-for` reading
  "Worked for 5s"; the same turn holding **only** the status row renders no `turn-worked-for` at
  all. 4 + 2 assertions, all passing, on today's `master`-side code with no part of this change
  implemented. The defect is therefore already latent — `runDurationsByRunId` supplies the duration
  from the lifecycle events — and task 2.2 is what makes it reachable, by creating turns whose only
  agent output is that row. Filed as **F269 (C)**; the finding carries the probe results in full.

  **Round RB reproduced this independently and then tried the two fixes RA proposed without
  trying.** Reproduction: 4 assertions on unmodified code, adding two cases RA did not run — the
  status row with *no* operator message at all (still no stat line), and a `thinking` row ahead of
  it (stat line present, the negative control). **One of the two proposed fixes does not work.**
  Excluding success-completion entries from `firstAgentBlockId` leaves it `undefined` in exactly
  F269's case, because the status row is the turn's *only* `agent_output` block and there is no
  later block to inherit the slot; `blockId === firstAgentBlockId` is then false for every block and
  the stat line is still absent. Measured: 2 of 6 assertions fail under it. The placement fix — have
  the success-completion branch return `<Fragment key={entry.id}>{durationLine}</Fragment>` instead
  of `null`, so the line survives the card it hung on — passes all 6, keeps the status row itself
  unrendered, still emits exactly one stat line when a text row precedes it, and leaves the 86
  existing assertions in `workingIndicator`, `agentTimeline`, `agentTimelineModel` and
  `agentHandoff` green. Task 4.5a now names that fix and drops the other.

D6 remains independent of D1-D5 in the sense that mattered originally: lifecycle events are already
persisted, so reading `Run` alone restores the label without it. What is no longer true is the
converse — D6 alone does not restore the indicator.

The writer to use is still `output_recording.record_agent_output` (`hub/hub/output_recording.py:22`),
which persists **and** broadcasts one row, so the two call sites collapse onto it rather than gaining
a second hand-rolled insert beside the existing `sse_manager.broadcast`.

### D7 — Coverage is exact by construction, not derived from a bound

**Chosen:** the run facts are read by id, so "every run the events name is in the map" is a property
of the query rather than an arithmetic claim about two limits. There is no bound to derive.

Round 2 created this decision to fix a real gap: D3 argued only that the map may describe *more*
runs than the events name, nobody had argued the other direction, and task 1.4 asked for "its own
limit" without naming one. Its remedy was to derive the run limit from the event limit — `log_q`
returns up to 50 `EventLog` rows, a run at the window boundary contributes one lifecycle event
rather than two, so up to 50 distinct runs can be named, so the run limit must be at least 50.

**Round 3 found that remedy insufficient, and insufficient in the direction it was written to
close.** The arithmetic is right and it is not the operative constraint: a limit only decides *how
many* rows come back, and coverage depends on *which*. Task 1.4 said `ORDER BY started_at DESC`,
and the recency of a run's row is not the recency of its events.

`run_reconciliation.reconcile_interrupted_runs` (`run_reconciliation.py:59-66`) selects **every**
`Run` still marked `running` — across the whole database, with no project scope and no time bound —
sets it `interrupted`, and calls `persist_event` for each. Those `EventLog` rows are stamped at
*restart* time. So one Hub bounce in a long-lived project writes a burst of `run_interrupted` events
for runs that started arbitrarily long ago, and those rows are now the **newest** events for their
agents. The returned event window is then dominated by old runs, while `ORDER BY started_at DESC
LIMIT 50` returns the fifty newest-*started* runs — a set that can be almost disjoint from them.

An implementation following round 2's tasks would therefore satisfy every word of D7 as written,
pass task 1.4b's test (which varies runs-per-window, not recency skew), and still present older
turns with no terminal outcome — F190's exact symptom, blessed once again by *An unknown run
degrades rather than fails*. The failure is one restart away in this repository's own dogfooding
project, and the change's own task 6.3 creates the mechanism deliberately, with a single run, which
is why it would pass.

The requirement *The run facts cover every run the events name* is unchanged in intent and was
already stated absolutely. What changes is that it is now met by construction rather than by an
argument about limits — which is the only form in which it can be checked by reading the query.

*Rejected: keeping the derived bound and adding an ordering argument to it.* Every candidate
ordering is an approximation of "which runs do the returned events mention", a set the route can
simply compute. Approximating an available answer is how the original defect was written.
## Risks / Trade-offs

- **11 UI test files mock the timeline response shape** → the largest mechanical cost. Move them in
  one commit, before touching the component, so a failure is attributable to the fixture rather than
  to the change. Named in `proposal.md` so this is planned rather than discovered.
- **`AgentActivityTab` and `AgentOutputPanel` also consume the shape** → they must be read before the
  hook changes. **Corrected in round 2:** they are not symmetric, and the original line here —
  "neither is expected to need run facts" — pointed the implementer away from the one component on
  the critical path. `AgentActivityTab.tsx:24,39` genuinely only unwraps, mapping the events into
  activity items. `AgentOutputPanel` is different: it holds the hook (`:330`) and its *only* other
  use of the value is passing it to `AgentTimeline` (`:1033`), which is where all three consumers
  live. Since `AgentTimeline` receives `timelineEvents` as a prop (`AgentTimeline.tsx:31`) rather
  than calling the hook itself, `AgentOutputPanel` must gain the `runs` map and thread it through as
  a new prop. It does not *read* the run facts; it is the only thing that can *carry* them.
- **A past turn's label can change on a later read**, because `Run.status` is present-tense and
  `run_reconciliation.py:65` flips `running → interrupted` when the Hub restarted mid-run → accepted:
  the only mutation after a run ends corrects a status that was wrong.
- **The route gains a fourth table, and after round 3 a second round trip** → the run query is a
  primary-key `IN` lookup over ids the route already holds, so it is the cheapest read of the four;
  `ix_runs_project_agent` (`models.py:1152`) is no longer what serves it. The cost is one sequential
  step after the `gather` rather than a fourth concurrent query, accepted in D3 because it is what
  makes coverage exact rather than approximate.
- **Duration figures shift when `runDurationsByRunId` goes** → `Run.started_at` predates the
  `run_started` event by the spawn, so every "Worked for Xs" grows; see D4. Re-baseline the
  component test rather than reconciling the two.
- **Breaking response shape with no consumer outside this repo** → the Hub UI is the only client;
  there is no published API contract for this route.
- **Deleting a correct function (`runDurationsByRunId`) risks regressing "Worked for 8s"** →
  mitigated by keeping its negative-duration guard and by asserting duration rendering in the
  component test, not only in a model test.

## Migration Plan

No data migration. `Run` rows already carry every fact the envelope reports, for every historical
run, so existing conversations begin rendering correctly on first read.

Deploy order within the change: schema and route first, then the hook, then the component, then
delete the model functions. Rollback is a revert; nothing is written that a previous version cannot
read, because nothing is written at all.

## Open Questions

- Whether the envelope's `runs` values should carry `error` (`models.py:1113`) as well, so a failed
  turn can say *why* rather than only *that*. Out of scope as written; it is one more column and the
  shape would not change.
- Whether `AgentActivityTab` should also present the terminal outcome, or whether the conversation
  remains its only surface.

## Round 2 corrections, 2026-09-01

Round 2 re-derived the argument against the code rather than re-reading round 1. Four corrections,
one alarm killed, and a list of what was checked and left standing.

**Changed:**

1. **The third consequence is unconditional, not reload-scoped** (`proposal.md`, and task 4.7).
   `anotherRunIsUnderway` is OR'd into `runVisiblyActive`, so it overrides `lastRunSettled` in every
   state, live included, whenever two or more runs sit in the event window. The gate collapses to
   `isRunning` — the pre-fix behaviour. Round 1 described it as both signals failing together on a
   reload, which is true but is the smaller half.
2. **D7 added** — the `runs` query needs a coverage bound derived from the event bound. D3 argued
   over-coverage was fine and nobody argued under-coverage, which the spec would then have excused
   as legitimate degradation.
3. **The `AgentOutputPanel` risk line was backwards** — it is the component that must carry the run
   facts, because `AgentTimeline` takes them as a prop.
4. **D6 names the writer.** `record_agent_output` already persists-and-broadcasts; the task said
   "persist in addition to broadcasting", which invites a second insert beside the existing
   broadcast rather than a substitution.

**Alarm raised and killed rather than filed.** `Run.status == "in_progress"` appears to occur, which
would break D5's enumeration and the `running -> started` boundary rename. It does not: `Run\.status`
matches inside `JobRun.status`, and every `skipped`/`in_progress` write in `scheduler.py`
(`:2580`, `:2609`, `:2762`, `:2884`) is under `run = JobRun(`. Filing this would have added a
mapping for two statuses that cannot reach the route. Recorded so round 3 does not re-raise it.

**Re-derived and left standing:**

- The central mechanism. `runStatusByRunId` is last-wins over the newest-first array; the oldest
  event wins; the oldest is `run_started`; `TERMINAL_LABEL['started']` is `undefined`.
- **No migration.** `Run` already carries `status` (`:1110`), `exit_code` (`:1112`), `error`
  (`:1113`), `started_at` and `ended_at`. No bulk `delete(Run)` exists anywhere in the Hub, and
  `scheduler.py:940` is `_discard_unused_run(session, run: JobRun)` — a `JobRun` a firing built and
  chose not to persist. "Run rows are never deleted" holds.
- **D4's claim that `runDurationsByRunId` is currently correct.** Its `if / else if` keeps
  `run_started` out of `endedAt`, and one run has one start and one terminal event, so last-wins
  cannot bite. Deleting it really is cleanup, not repair.
- **The misleading test.** `agentTimelineModel.test.ts:223-235` feeds `run_started` before
  `run_completed` — ascending, the opposite of the route — and asserts `'completed'`.
- **The 11-file blast radius**, exactly: nine mock `useAgentTimeline`, plus `workingIndicator`
  (which imports `runDurationsByRunId` directly and so breaks on deletion) and `agentTimelineModel`.
  A case-sensitive grep for `timeline` undercounts this to five; the hook is `useAgentTimeline`.
- Every backend line citation: `agents.py:729-801`, `agent_trigger.py:1677` / `:2001-2006` /
  `:2129-2142` / `:2723-2736`, `models.py:1110` / `:1152`, `agentTimelineModel.ts:112-118` /
  `:138-168` / `:187-199`, `agents.ts:387-392`.

**Stale UI line numbers, corrected throughout:** terminal label `:202` -> `:220`; `lastRunSettled`
`:116` -> `:114`; `anotherRunIsUnderway` `:133` -> `:131`; the settled-signals comment `:96-112` ->
`:88-113`; task 4.7's `:118-136` -> `:117-137`.

## Round 3 corrections, 2026-09-01

Round 3 read `agentTimelineModel.ts`, `AgentTimeline.tsx`, the timeline route, the `Run` model,
`agent_trigger.py`'s five terminal sites and `run_reconciliation.py` against this proposal, before
reading either round's own reasoning. Two things did not survive.

**1. D3 is reversed and D7 is rewritten — the run query's *ordering*, not its limit, decides
coverage.** Round 2 correctly found that the run bound had to be derived rather than picked, and
derived it. But a limit governs how many rows return, not which; task 1.4's `ORDER BY started_at
DESC` ranks runs by when they *started*, and the events that name them are ranked by when they were
*written*. `reconcile_interrupted_runs` decouples the two on purpose: it sweeps every `running` row
in the database at Hub start and stamps a `run_interrupted` event at restart time, so one bounce
makes the newest events for an agent name its oldest runs. An implementation obeying round 2's
tasks to the letter would omit exactly those runs, satisfy D7 as written, pass task 1.4b, and
present older turns with no terminal outcome. Reading the ids off the merged events and looking
them up by primary key removes the question instead of answering it. This is the second time in
this change that a value the server already knows was going to be approximated on the strength of
an ordering — which is what F190 is.

**2. D4's "the same fact, recorded" is not exact.** `Run.started_at` is stamped at row construction
inside the trigger request (`agent_trigger.py:1073`); the `run_started` event is written after the
pty exists (`:1857-1864`). Every duration therefore grows by the spawn cost, and a run whose spawn
failed gains a duration it does not have today. The change adopts the row's figure deliberately —
it is named here so task 4.5 re-baselines rather than reconciles.

**Re-derived and left standing** — do not re-raise these:

- The central mechanism. `runStatusByRunId` (`agentTimelineModel.ts:186-199`) is last-wins over the
  route's `reverse=True` array (`agents.py:800`), so the oldest event wins, the oldest is
  `run_started`, and `TERMINAL_LABEL` (`AgentTimeline.tsx:56-60`) has no `started` key. Verified at
  the render site: `:202` reads `statusByRun[turn.runId]`, `:220` indexes `TERMINAL_LABEL` with it.
- Round 2's correction 1. `runVisiblyActive = isRunning && (!lastRunSettled || anotherRunIsUnderway)`
  (`:139`), and `anotherRunIsUnderway` (`:131`) is true whenever a second run sits in the window,
  since every run reads `started` and `started` is not in `TERMINAL_STATUSES`. Re-derived from the
  three lines alone. Stands.
- Round 2's correction 3, and more strongly than it was stated. `AgentActivityTab.tsx:24` does not
  merely receive the value — it calls `useAgentTimeline` itself and maps the array at `:39`, so it
  is a second independent hook holder that breaks on the envelope. Task 3.3 covers it.
- The 11 test files. `grep -rln 'useAgentTimeline\|agentTimelineModel\|runDurationsByRunId\|runStatusByRunId' hub/ui/src/__tests__`
  returns exactly the 11 named.
- Every `Run` column the envelope reports exists with the right nullability — `status`, `exit_code`,
  `error`, `started_at` (NOT NULL), `ended_at` (nullable) — and all six sites that set a terminal
  status set `ended_at` with it (`agent_trigger.py:1804`, `:2035`, `:2213`, `:2571`, `:2648`,
  `run_reconciliation.py:66`). `ended_at` is populated wherever a status is terminal.
- D5's enumeration, by a second route. `run_interrupted` is deliberately **absent** from
  `_RUN_LIFECYCLE_EVENTS` (`agent_trigger.py:1674`), which `_broadcast_run_lifecycle` asserts
  against; reconciliation writes it through `persist_event` instead. The client's
  `LIFECYCLE_EVENT_STATUS` still covers all five, and D5 is unaffected.

**One alarm raised and killed rather than filed.** `proposal.md`'s Impact section cites `:202`,
`:116` and `:133` where `design.md` cites `:220`, `:114` and `:131`, which reads as round 2 having
missed three stale numbers. It did not: the proposal names the three lines that *read* `statusByRun`
and the design names the three that *declare* what reads it. Both sets are correct against the
current file. Do not "fix" either.

### Supplementary pass, 2026-09-01 — phase 2 and the fixture claims

Round 3's first sitting read phases 1 and 4 closely and left phase 2 and the test-fixture claims
unread. Both findings above came out of the code that *was* read, which is exactly the bias worth
distrusting, so this pass covered the rest. It found one thing that changes the proposal's central
account and three that change tasks.

**SUPERSEDED 2026-09-02 by phase 0 task 0.3 and by round RA — this finding is false and D6 is
re-argued above.** It is kept unedited below because the shape of the mistake matters: the
producer it traced (`agent_trigger.py`'s finalize broadcast) really is broadcast-only, and the
conclusion drawn from that — that no row of the shape is ever persisted — did not check for a
second producer. `runner_parsing.py:356` is the second producer. Everything the paragraph says
about `useAgentChatHistory` and about `entries` coming only from persisted rows is correct; only
the inference from it is wrong.

**The first settled-signal has never fired, for anyone.** `AgentTimeline.tsx:88-113` documents two
terminal signals — the streamed status entry, which "lands the instant the run ends", and the
lifecycle event, which "arrives late". The first does not exist. The status row is broadcast over
SSE and never written to `AgentOutput`; `entries` are supplied by `useAgentChatHistory`, which on
an `agent_output` event calls `invalidateQueries` and nothing else (`agentChat.ts:296-312`), so the
list is always a fresh read of persisted rows. A row that was never persisted never becomes an
entry. `isSuccessCompletionEntry` has therefore never matched, `lastRunSettled` has always been
`false`, and

```
runVisiblyActive = isRunning && (!lastRunSettled || anotherRunIsUnderway)
```

collapses to `isRunning` through the **left** branch, unconditionally, for every agent.

This subsumes round 2's correction 1 and contradicts its scope. R2 derived the same collapse from
`anotherRunIsUnderway` and concluded it needed two or more runs in the window, adding that "a
single-run conversation is unaffected, which is why this survived manual review". Round 3's first
sitting re-derived that and let it stand. Both were reading one disjunct. A single-run conversation
is affected too, by the shorter path. The evidence was already in round 1's own measurement —
`/agents/{name}/output` holds no status row for a stopped run — and nobody joined it to the fact
that `entries` come only from the database.

The practical consequence is that **task 2.2 is load-bearing for the working indicator**, not just
for a durable exit code, and task 4.7's single-run case must assert a change rather than assert
nothing changed.

**Three smaller corrections, all recorded in `tasks.md`:**

- `record_agent_output` hardcodes `id=f"out-{short_id()}"` (`output_recording.py:81`), so task 2.2's
  "field-for-field" broadcast equality is unobtainable on `id`. The key set is otherwise identical,
  and nothing in `hub/ui/src` keys on `status-{run_id}`, so the substitution is safe as long as the
  task stops demanding an equality that cannot hold.
- Task 2.2's stated reason for preserving the payload shape — `AgentOutputPanel`'s Handoff scan —
  describes a consumer that was **deleted** (`AgentOutputPanel.tsx:148-151`, `:252-259`). The
  `agent_trigger.py` comments still assert it. The shape that must actually be preserved is the
  persisted row's, for `isSuccessCompletionEntry`.
- The 11-file blast radius is real and its cost was mis-stated. Nine files carry one identical line;
  the work is in `workingIndicator.test.tsx` and `agentTimelineModel.test.ts`. Worse, the nine would
  stay green un-updated, because `AgentOutputPanel` destructures with `= []` — the change's own
  testing requirement, violated by its own fixtures.

**Verified and standing.** `agentTimelineModel.test.ts:223-235` does feed `run_started` before
`run_completed` and assert `'completed'` — ascending input to a descending route. The proposal's
claim and its line numbers are exact. `record_agent_output` does persist and broadcast one row with
a matching key set. Every `Run` column the envelope reports is populated at all six terminal sites.
No spec change follows from this pass: *A run's terminal status line is persisted* says "recoverable",
not "displayed", and the visible-outcome requirement is served by the `runs` map.

### Final read, 2026-09-01 — what the last sitting checked

Three things, all confirming or tightening what is already here rather than reopening it.

**The repair works end to end, which had been assumed and not traced.** The finding above — that
`lastRunSettled`'s first signal has never fired — is only actionable if persisting the row makes it
fire. It does: `_output_to_timeline` (`agent_chat.py:213-223`) maps `AgentOutput.kind` onto
`output_kind` and carries `payload` and `run_id` through, so a row written by `record_agent_output`
with `kind="status"` and `payload={"phase": "completed", ...}` satisfies `isSuccessCompletionEntry`
exactly. `TimelineEntry.delivery_state` defaults to `"delivered"` (`agent_chat.py:70`) and
`_output_to_timeline` does not override it, so the row survives `groupIntoTurns`' delivered-only
filter and joins its own run's turn. **Narrowed by round RA, 2026-09-02:** the mechanism trace above
is correct and was re-verified against `agent_chat.py:213-223` and `:70`; its conclusion was not.
Task 2.2 makes signal 1 fire for a run that did *not* complete, which is the case where it has never
fired. For a run that completed it fires already, from `runner_parsing.py:356` — see D6 as re-argued.

**`test_bola.py` is a sharper break than "the shape changed".** The timeline sits inside a loop
asserting `isinstance(data, list)` across nine endpoints, and it is the route's only cross-project
isolation coverage. The envelope forces it out of that loop, and the lazy fix — deleting the path
from the list — silently removes the coverage at the same moment the response gains a new map of
run facts to leak. Task 1.6 now says what to write instead.

**D3's first draft dropped a predicate it should not have.** Recorded above rather than quietly
corrected, because "the ids already came from filtered rows" is exactly the kind of reasoning that
is true today and stops being true when someone writes a new event source.
## Phase 0 observations, 2026-09-01 — one decision's premise did not survive

The operator approved this change on the condition that the defect be observed live first. It was,
on a fresh fixture project against a Hub on 8011; the full write-up with timings and database reads
is `scripts/drive/FINDINGS.md`, *F190 phase 0 — the observation gate, driven 2026-09-01*. Four of
the five observations held. One did not.

**D6's round-3 correction is false as written, and D6 survives on a narrower argument.** The
correction says *"a row that is only broadcast never becomes an entry, so `isSuccessCompletionEntry`
has never matched anything, in any state."* Measured: a completed run's conversation contains
exactly one matching entry, `payload={"version": 1, "phase": "completed", "summary": "Completed"}`,
and the working indicator on a single-run conversation went out **on the same snapshot the answer
text landed** — 0.7 s before the roster poll, which is the atomic handover
`AgentTimeline.tsx:88-113` was written to produce.

The error is an identification. Round 3b traced the terminal status line at `agent_trigger.py:2135`,
which is indeed only broadcast, and concluded that no entry of that shape exists. The entry that
satisfies the predicate is written by something else — the stream parser's own
`status_event("completed", ...)` — and is persisted. `FINDINGS.md` already carried that measurement
("A refinement to F190's second half") before round 3b was written.

**What this leaves.** Signal 1 works, but only for a run that *finishes*. A stopped run has no
`status` row at all (measured: nine output rows for the agent, three of `kind="status"`, none of
them the stopped run's), so `lastRunSettled` is False for the whole life of that conversation and
the gate collapses to `isRunning`. D6's *purpose* is intact; its stated reason is not. A round must
re-argue it from the measured premise — signal 1 has never worked **for a run that did not
complete** — before phase 1 is implemented. `tasks.md` carries the block.

**Confirmed unchanged, and not to be re-derived by that round:** the terminal label is absent for a
stopped run and for an interrupted one, live (0.2); the timeline route returns newest-first and
`runStatusByRunId` therefore reports `started` for every run in every snapshot (0.2, 0.4); the
lingering-tail regression fires whenever two or more runs sit in the event window (0.4); the label
is still absent on reload and the stopped run has no persisted `status` row (0.5); and
`run_interrupted` carries restart time while `Run.started_at` stays old — 107.3 s apart, a gap equal
to the outage and to nothing about the run — which is the decoupling D3's reversal rests on (0.6).
The *miss* D3 protects against was not reproduced; it needs more runs than a drive can usefully
spend, and only the decoupling and the unbounded sweep (`run_reconciliation.py:59`) were measured.

## Round RA, 2026-09-02 — D6 re-argued from the measured premise, and the block lifted

Phase 0 task 0.3 falsified round 3b's premise for D6 and `tasks.md` blocked phases 1-7 until a round
re-argued it. This is that round. It read `AgentTimeline.tsx`, `agentTimelineModel.ts`,
`runner_parsing.py`, `runner_events.py`, `output_recording.py`, `agent_chat.py`,
`run_reconciliation.py` and both terminal paths in `agent_trigger.py` **before** reading round 3b's
reasoning, then compared. It did not re-derive what phase 0 confirmed (0.2, 0.4, 0.5, 0.6), per the
block's own instruction.

**The re-argument is in D6 above.** In one line: signal 1 works, and it works for the run that
finished, because a *second* producer — the stream parser at `runner_parsing.py:356` — writes a row
of the same shape and that one is persisted. D6's purpose survives; its weight changes. It is not
what repairs the gate (D1-D5 are), and it is not a first-time repair of signal 1 (it is an extension
of signal 1 to runs that did not complete), and it cannot reach the `interrupted` outcome at all.

**Three things this round found that no earlier round had, all consequences of the corrected
premise rather than of re-reading the old one:**

1. **`interrupted` is outside D6's reach.** `reconcile_interrupted_runs` writes an `EventLog` row
   and no `AgentOutput`. Task 2.1 was ambiguous about which outcomes it asserts; it now names the
   two spawn paths and explicitly excludes the reconciliation path. Without this, the phase-7 round
   would have gone looking for a status row that correctly does not exist.
2. **A completed run will carry two `phase="completed"` rows after task 2.2.** Both render `null`,
   so it is invisible; the exit code lives on only one of them. Stated in D6 and asserted in a new
   task 2.1a so a later reader does not "clean it up" and delete the signal that works today.
3. **The invisible row can swallow the turn's stat line.** `firstAgentBlockId` selects the first
   `agent_output`-carrying block, a `status` entry is its own block (`RESULT_OUTPUT_KINDS`), the
   `durationLine` renders inside that block's fragment, and that fragment is `return null` for a
   success-completion entry. So for a turn whose only agent output is the newly persisted row —
   a run stopped before producing anything, or a failed spawn — "Worked for Xs" vanishes. Task 4.5
   hands those exact runs a duration for the first time, so the two halves of this change meet
   precisely on the case neither considered. New task 4.5a, and a new scenario in
   *A run's terminal outcome is visible*.

**What this round changed nothing about.** D1, D2, D3, D4, D5 and D7 were re-read against the code
and stand unedited: the route still never reads `Run`; `runStatusByRunId` is still last-wins over a
newest-first array; `run_reconciliation.py:59` still sweeps the whole database with no project scope
and no time bound, so D3's reversal and D7's construction argument are untouched; `Run.status` is
still `{running, completed, failed, stopped, interrupted}`. The proposal's headline — F190 — is
unaffected in every particular. Saying so explicitly is part of the round: a round that reports only
what it changed makes the next one look cheaper than it is.

**Scope decision: the change is not narrowed.** The block asked for one or the other. Everything
phase 1 through phase 7 proposes still follows from the corrected premise — the label, the envelope,
the coverage property, the persisted exit code and the deleted reducers are all untouched by the
identification error. What changed is the *reason* given for one decision and the *weight* carried
by one task, and both are now stated from what was measured. Phases 1-7 are unblocked, with the
three new tasks above added.

## Round RB, 2026-09-02 — RA's facts hold; its scope does not, and one proposed fix does not work

An independent re-derivation of round RA's repaired argument, not a re-read of it. It opened
`AgentTimeline.tsx`, `agentTimelineModel.ts`, `runner_parsing.py`, `runner_events.py`,
`output_recording.py`, `agent_chat.py`, `run_reconciliation.py`, `runner_commands.py`,
`codex_appserver.py` and both terminal paths in `agent_trigger.py` **first**, formed its own account
of which runs get a persisted `kind="status"`/`phase="completed"` row, and only then read D6 and the
*Round RA* section.

**What RB confirmed, by a stronger route than RA used in each case.**

- *The finalize broadcast is reached for every outcome the finalize block sees.* It sits inside the
  `async with async_session_factory() as db:` at `agent_trigger.py:2009`; the `if run:` guard closes
  at `record_turn_usage`, well above it. Reached for `stopped`, `failed`, `completed` and the
  binding-conflict case (`:2000-2007`). Confirmed. The app-server path has the identical broadcast
  at `:2718-2733`, which RA cited but did not check the guard structure of; it is likewise
  unguarded.
- *`interrupted` cannot gain a status row.* RA argued this from one module. RB checked every writer
  of the literal instead: `Run.status = "interrupted"` is assigned in exactly one place in the Hub
  (`run_reconciliation.py:65`), and `codex_appserver`'s own `interrupted` turn outcome is mapped to
  `stopped`, not to it (`agent_trigger.py:2628`, `:2673`). `record_agent_output` appears nowhere in
  `run_reconciliation.py`. Confirmed, and now confirmed exhaustively rather than locally.
- *F269's mechanism.* Reproduced by running, not by reading — see the measurement recorded under D6.

**What RB changed. RA's facts are all correct; the scope it drew around them is not.**

RA found the second producer and then generalised it to the product. `parse_claude_line` is selected
only for the three Claude-family runner values (`agent_trigger.py:1867`); `SUPPORTED_RUNNERS` is
`("claude", "claude_proxy", "native", "codex")` (`runner_commands.py:52`); and neither Codex
transport emits a completion sentinel. `status_event("completed")` occurs exactly once in the Hub.
So D6's table is Claude-only and did not say so, and RA's headline retraction — "not a first-time
repair of signal 1" — is true for Claude and **false for Codex, for every outcome including a clean
completion**. This is the shape the round discipline exists to catch: an argument wrong about
something every one of whose individual claims is right.

Four downstream corrections follow, all in `tasks.md`: 2.1's stated *reason*, 2.1a's duplication
assertion, 4.7's "single-run, completed: assert it does NOT change" regression guard, and a new
task 2.1b for the runner the corrected table exposes. The spec gains one scenario, *It does not
depend on the runner announcing its own completion*.

**And one proposed remedy is withdrawn.** Task 4.5a offered two fixes for F269 as equivalents. RB
implemented each against the real component and ran them: the `firstAgentBlockId` exclusion does not
fix the case it was written for. Recorded under D6 with the measurement.

**What RB changed nothing about, said out loud.** D1, D2, D3, D4, D5 and D7 stand unedited — RB
re-read each against the code and had nothing to add to RA's own statement that they were untouched.
D6's *purpose*, its choice of writer (`record_agent_output`), its exit-code argument, and its
"D6 does not repair the gate" conclusion all survive unchanged; so does every part of the F269
analysis except the fix menu. Phases 1-7 stay unblocked. The scope decision — not narrowed — stands,
and RB did not revisit it.

## Phase 2 as built, 2026-09-02 — task 2.4 answered by measurement, and the premise re-checked

Task 2.4 asked whether an invisible row is what this change means to ship, rather than something
arrived at by accident. It is, and the check that says so is now recorded rather than reasoned.

**The row is invisible for every outcome, measured on the component.** Two assertions were added to
`agentTimeline.test.tsx`: the pair a completed Claude run now ends with (the parser's `Completed`
and the finalize block's `Run completed (exit 0).`) draws neither line, and a stopped run's
`Run stopped (exit 15).` draws none either. Both were mutation-checked — with
`AgentTimeline.tsx:430`'s `return null` removed, both fail and the pre-existing successful-run
assertion fails with them (3 of 41 in that file). So the branch that hides it is the reason they
pass, not an accident of the fixture.

**`phase` has exactly one reader in the product, and 2.4's warning is therefore cheap to honour.**
2.4 says not to make `phase` outcome-dependent without checking every other reader. There are none:
`payload.phase` on an agent-output row is read only by `isSuccessCompletionEntry`
(`agentTimelineModel.ts:27`), reached from `AgentTimeline.tsx:115` and `:430`; a grep of `hub/hub`
for `["phase"]`, `get("phase")` and `phase ==` returns spec-lifecycle hits and nothing else. The
consequence is not that changing it would be safe — it is that the single reader is
`lastRunSettled`, and making `phase` outcome-dependent would take the settled signal away from
exactly the stopped and failed runs this phase exists to give it to.

**The stale justification in the code is now gone, and it was stale.** Both call sites claimed
removing the broadcast "would silently break" AgentOutputPanel's Handoff flow. That effect is
deleted, in terms, at `AgentOutputPanel.tsx:148-151` and `:248-259`. The comments now name
`lastRunSettled` as the consumer whose shape must be preserved.

**One behaviour change beyond the row itself, stated rather than discovered later.**
`record_agent_output` broadcasts `agent_session_changed` when the row it writes is the first output
of its session (`output_recording.py:112-115`). A run that ended without producing any output — a
stop before the first line, a spawn that ran and wrote nothing — now trips that on its terminal
status row. The frontend answers by refetching the agent's session list, which is correct for a
session that genuinely has its first row; it is one extra SSE frame in a case that previously
produced none.

**What the commit's own measurement showed about D6's table.** The six new Hub tests were run
against unmodified code first. The completed-Claude test failed `1 == 2` — the parser's row is
there and the finalize block's is not — and the completed-Codex test failed `0 == 1`. That is the
Claude row and the Codex row of D6's table, observed rather than read, and it is the first time
either has been asserted in the suite.

## Phase 7, 2026-09-03 — what the verification round found

A sitting that did not write the code re-ran phase 0's observations against the built product
(`scripts/drive/t_aturn_p7.py`, 29 checks, 0 failed) and read the route, the isolation test and the
four artifacts. Every observation moved the way the change said it would, and the round found two
things the implementation had not been asked about.

**The isolation test could not fail for the reason it existed.** Task 1.6 added a `Run` row to
`test_bola.py`'s Project A fixture so that `timeline["runs"] == {}` "would not be vacuous". It was
still vacuous: Project B owns no event naming that run, so `run_ids` is empty and the map is `{}`
whether or not the route filters by project. Measured — deleting `Run.project_id == project_id`
left the file green at 4 passed. The leak the predicate prevents needs an event *in Project B*
naming a run *in Project A*; with one written, the unfiltered query hands Project A's run facts to
Project B's key and the assertion fails. The bait is synthetic and no product path is known to
write such a row, which is the point: the route's comment calls the predicate *enforcement, not
inference*, and there is now a test that enforces it rather than one that agrees with it.

**F269's shape stopped being uncommon, and no test rendered the version production emits.** F269
was filed Severity C on reachability — "a stopped or failed run cannot hit it, because it has no
`status` row in the first place" — with the note that task 2.2 would change that. It did.
Measured at three stop delays: a stopped run's conversation holds **exactly two entries**, the
operator's message and the terminal status row, with no `thinking` row ahead of it. So
`firstAgentBlockId` is the status entry's block on **every** stopped turn, and
`isSuccessCompletionEntry` matches it, because the persisted row reads
`{"phase": "completed", "exit_code": 2}` — `phase` means the run ended
(`agent_trigger.py:2141-2145`), and the outcome is the run row's.

That has a consequence D6 argued for and nothing had watched: **signal 1 now fires for a stopped
run.** It is visible in the drive's own transition record — the phase-0 model reports
`settled=False` on the first read after the stop and `settled=True` on the reload, from a status
row that did not exist before task 2.2.

It also means the stopped-and-silent turn is where two requirements meet: it must draw the terminal
label (*A stopped run says it was stopped*) **and** keep its duration line (*A turn that produced
nothing still reports what it cost*), on a block whose fragment used to return `null`. Task 4.5a's
fixture is a *completed* run, which draws no label, so nothing asserted the two survive together.
A test for the measured shape was added to `timelineRunFacts.test.tsx`; reverting 4.5a's fragment
kills it and the original both.

**One harness note, because it cost a leg.** `session_mode` accepts only `new` or `resume`
(`agent_trigger.py:1226`). A second turn in the same conversation is requested by naming
`conversation_id`. Passing `"continue"` returns 400, and a multi-run leg that does not assert on
the second trigger's `run_id` will happily go on to measure one run and pass.

**Fourth time this window that the first red result was the apparatus, not the product.** The new
component test failed on `getByText('Turn stopped')` — the label is a text node beside `· 01:00` in
the same element, so the exact-string matcher missed text that was rendering correctly. The rest of
the file already used `/Turn stopped/` for that reason.
