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
label (`AgentTimeline.tsx:202`), `lastRunSettled` (`:116`), `anotherRunIsUnderway` (`:133`) and the
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
Persisting it restores the *first* of the two settled-signals in `AgentTimeline.tsx:96-112` and makes
the exit code durable.

This is independent of D1–D4: because lifecycle events are already persisted, reading `Run` alone
restores the label. What D6 uniquely adds is the exit code and the in-stream sentence.

## Risks / Trade-offs

- **11 UI test files mock the timeline response shape** → the largest mechanical cost. Move them in
  one commit, before touching the component, so a failure is attributable to the fixture rather than
  to the change. Named in `proposal.md` so this is planned rather than discovered.
- **`AgentActivityTab` and `AgentOutputPanel` also consume the shape** → they must be read before the
  hook changes; neither is expected to need run facts, but both unwrap the response.
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
