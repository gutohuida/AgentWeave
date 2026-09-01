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

### D3 — The `runs` map is scoped by agent, not narrowed to the returned events

The fourth query runs inside the same `asyncio.gather` as the other three and therefore cannot know
which run ids the merged events reference. Narrowing would require merging first and issuing a
second query, serialising the gather to save a few hundred bytes.

The map may therefore describe runs no returned event names. This is stated in the spec so that it
reads as intent rather than as an oversight to be optimised away later.

### D4 — Both reducers go, not one

`runDurationsByRunId` (`:138-168`) is currently **correct** — it splits `run_started` from terminal
events into two maps and combines at the end, so ordering cannot hurt it. Retiring it is cleanup,
not repair, and it is included deliberately: leaving one function that still derives run facts from
the event array, immediately beside the one just deleted, is the half-migration that produced this
adjacency in the first place. `Run.started_at` and `Run.ended_at` are the same fact, recorded.

The negative-duration guard that function carries (a clock that went backwards yielding
"Worked for -3s") must be preserved at the new call site; the concern does not disappear with the
function.

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

This is independent of D1–D4: because lifecycle events are already persisted, reading `Run` alone
restores the label. What D6 uniquely adds is the exit code and the in-stream sentence.

### D7 — The `runs` map must cover every run the event window can name

**Chosen:** the run query's limit is bound to the event limit rather than picked independently —
it must be at least as large as the number of distinct runs the returned events can reference.

D3 argues one direction only: the map may describe runs no returned event names, and that
over-coverage is deliberate. Round 2 found nobody had argued the other direction, and the risk
there is not cosmetic. `log_q` returns up to 50 `EventLog` rows; a run normally contributes two
lifecycle events, but at the window boundary it contributes one, so **up to 50 distinct runs** can
be named by the events in a single response. A run query limited to fewer than that silently drops
the oldest of them.

What makes it dangerous rather than merely wrong is that the spec already blesses the result. *An
unknown run degrades rather than fails* says the client "presents that run exactly as it presents a
run with no outcome yet" — which is precisely the F190 symptom. A limit chosen carelessly would
therefore ship this change, satisfy its own specification, and still show no terminal label on
older turns. The requirement now states the relationship so the limit cannot be chosen in
isolation.

*Rejected: no limit at all.* Correct and simplest, but an agent with thousands of runs would
serialise a full scan into a route whose other three queries are all bounded. The bound exists;
it just has to be derived from the event bound rather than invented.

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
- **The route gains a fourth table** → mitigated by using the existing composite index
  `ix_runs_project_agent` (`models.py:1152`) and by keeping the query in the same `gather`, so the
  added latency is one concurrent indexed `SELECT`, not a serial one.
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
