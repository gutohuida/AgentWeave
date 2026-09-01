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
`select(Run).where(Run.id.in_(run_ids))`, a primary-key lookup with no limit and no ordering.
An empty id set skips the query entirely.

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

### D6 — The status row is persisted at both call sites, and is a separate concern

`agent_trigger.py:2129-2142` (process path) and `:2723-2736` (app-server path) construct an
`agent_output` payload with `id=f"status-{run_id}"` and `kind="status"` and only broadcast it.
Persisting it restores the *first* of the two settled-signals in `AgentTimeline.tsx:88-113` and makes
the exit code durable. The writer to use is `output_recording.record_agent_output`
(`hub/hub/output_recording.py:22`), which persists **and** broadcasts one row — so the two call
sites collapse to it rather than gaining a second, hand-rolled insert beside the existing
`sse_manager.broadcast`.

This is independent of D1-D4: because lifecycle events are already persisted, reading `Run` alone
restores the label. What D6 uniquely adds is a durable exit code and a working `lastRunSettled`.

**Two corrections from round 3's supplementary pass.** First, D6 does not *restore* the first
settled-signal — it makes it work for the first time. `entries` reach `AgentTimeline` only through
`useAgentChatHistory`, which invalidates and refetches with no optimistic append
(`agentChat.ts:296-312`), and the chat route builds them from persisted `AgentOutput` rows. A row
that is only broadcast never becomes an entry, so `isSuccessCompletionEntry` has never matched
anything, in any state. See the round 3 corrections section for what that means for the gate.

Second, D6 does **not** add an "in-stream sentence". Both call sites hardcode
`payload={"phase": "completed"}` whatever the outcome, on purpose (`agent_trigger.py:2125-2126`),
and `AgentTimeline.tsx:430` returns `null` for every entry `isSuccessCompletionEntry` matches — so
the persisted row is invisible for a stopped and failed run exactly as it is for a completed one.
The visible outcome comes from the `runs` map's terminal label, not from this row.

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
