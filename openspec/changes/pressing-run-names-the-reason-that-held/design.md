# Design — pressing Run names the reason that held

**Round 1, 2026-09-23** (day window, D-2b). F400 and F373, re-measured on `dcdf723` with
`scripts/drive/d2b_0923_run_answer_probe.py`. To re-run it, copy it under `hub/tests/` as
`test_zz_probe_*.py` and run it with `-s`. It prints what the route answers and asserts nothing about
the right answer. **Nothing here is implemented yet.**

## Context

`run_job` (`hub/hub/api/v1/jobs.py:1326-1464`) fires the job through the scheduler with the route's
own session: `scheduler._fire_job_internal(job, trigger="manual", session=session)`, at `:1372`.
When that returns `False`, the branch at `:1383-1453` turns the decline into an HTTP answer. It
cannot ask the firing why, because several declines deliberately write nothing. Every `return False`
in `_fire_job_internal` (`scheduler.py:2908-3466`), read in R1:

| Path | Line | Writes a `JobRun`? | What the route answers today |
|---|---|---|---|
| Busy guard (`_loop_flow_busy_reason`) | `:2984-2998` | **no** | Re-asks the guard: `{busy}, and {why}. Nothing was started.` (409) |
| Agent skip (`_job_agent_skip_reason`) | `:3017-3037` | yes, `skipped` | That row's reason (409) |
| Plain job held, first firing | `:3061-3079` | yes, `skipped` | That row's reason (409) |
| Plain job held, later firings | `:3049-3060` | **no**, counts `tick_count` into the newest row | That row's reason (409), correctly |
| Loop stop reached | `:3088-3155` | yes, `skipped` | That row's reason (409) |
| In flight (`DECISION_IN_FLIGHT`, F23) | `:3193-3208` | **no** | **The newest row's reason if it is `skipped` (F373)**, else the in-flight answer |
| Stall, first firing | `:3243-3264` | yes, `skipped` | That row's reason (409) |
| Stall continues (D6 of `loop-notices-and-reacts`) | `:3222-3242` | **no**, counts `tick_count` | That row's reason (409), correctly |
| Exception after `run` exists | `:3444-3464` | yes, `failed` | 500 with its summary |

The route tells "this press wrote the row" apart from "an earlier firing wrote it" by comparing the
newest row's **id** before and after (D11 of `a-spent-allowance-holds-the-queue`, `:1363-1375`). A
counted stall keeps the id, so by id it looks exactly like a decline that wrote nothing. The
`skipped` branch at `:1410-1414` is therefore left ungated. It is right for the two counting paths
and wrong for the in-flight one, which is F373.

**The busy guard** (`scheduler.py:312-350`) refuses when the job's agent is running or held **and**
one of three things holds. It asks them in this order:

1. The loop holds no non-terminal task (`_loop_has_open_task`, `:295-309`).
2. The loop declares no specification document. `_agents_a_loop_may_staff` returns `[]` for it
   (`:1240-1261`), so the pool is empty whoever is free.
3. The loop is a flow and `_agents_that_are_free` is empty.

It returns only the busy sentence. The route then re-derives which half held with a second
`_loop_has_open_task` query (`:1401-1405`), and it can tell only (1) from not-(1). It files (2) under
(3). That is F400.

**Measured on `dcdf723`** (probe, `live_scheduler`, `schedule_agent` stubbed):

| Case | Route answer today |
|---|---|
| documentless, open task, owner mid-turn, a sibling free | 409 `…running a turn, and no other agent is free to take this loop's work.` — **false** |
| documentless, empty queue, owner mid-turn, a sibling free | 409 `…running a turn, and this loop's queue holds no open task for another agent to take.` — trailing clause wrong for this loop |
| flow, open task, owner mid-turn, nobody else | 409 `…and no other agent is free to take this loop's work.` — true |
| flow, only task `in_progress` under the owner, owner mid-turn, a sibling free, an hour-old `skipped` row | 409 `loop queue is stalled: 1 still awaiting a prerequisite's approval` — **false (F373)**. The earlier row keeps `tick_count=1` and its requester |
| continuing stall, pressed twice | 409 with the stall reason both times; one row, `tick_count` 1→2. Correct |
| **identity**: in one session, read the newest row, fire, read again | `latest is earlier` → `True`; `earlier.tick_count` 1→2 **in place** |

The last row is the constraint on D3. The session factory is `expire_on_commit=False`
(`db/engine.py:163`), and `_stall_run_to_increment` returns the identity-mapped instance the route
already holds. The route's `earlier_run` object **is** the counted row. So F373's ledger sketch,
*"read the newest row's `tick_count` together with its id"*, works only if the value is copied out
before the firing. Comparing `latest_run.tick_count` with `earlier_run.tick_count` afterwards
compares an object with itself and always reads "unchanged".

**The board is already right** (archived design's Open Question 2, answered). For the documentless
open-task case, `decide_firing` answers `stalled` with `loop queue is stalled: no claimable task
among 1 open (1 pending)` (`_stall_reason_from_walk`, `scheduler.py:2196-2234`). `jobs.py:357`
replaces that with the busy sentence, and the probe read `probe-owner is already running a turn`
on the board. The busy sentence alone names no roster, so it is true. The board needs no edit here.

**Who reads the route's answer.** The MCP tool `run_job` (`mcp_server.py:929-937`), which returns
the Hub's answer to the calling agent, and any API client. **The app's own Run button does not
display it** (`JobsPage.tsx:157`, `onRun={runJob.mutate}`, no `onError`; filed as F411, Open Question 1).

## Goals / Non-Goals

**Goals.** Every 409 `run_job` gives names the condition that actually refused, and no condition
that did not. The route answers from a firing record only where this press wrote it or counted into
it.

**Non-goals.**
- The UI (F411). Displaying the answer in the app is a separate, bundle-touching change.
- The firing's own behaviour: who is staffed, what is written, what is counted. Not one decision
  in `_fire_job_internal` moves.
- The board's stall label, which is already true (above).
- The 500 path for a plain job that genuinely failed.

## Decisions

### D1 — The guard says which half refused; the route stops re-deriving it

Add to `scheduler.py`:

```python
#: Which half of the busy guard's second condition held (design D1). Asked in this order.
BUSY_EMPTY_QUEUE = "empty_queue"
BUSY_LOOP_SCOPE = "loop_scope"          # the loop declares no document: its work goes to one agent
BUSY_NO_FREE_AGENT = "no_free_agent"    # a flow whose pool is empty


class LoopBusyRefusal(NamedTuple):
    reason: str   # `_loop_agent_busy_reason`'s sentence, unchanged
    held: str     # one of the three constants above


async def _loop_flow_busy_refusal(session, loop, agent) -> Optional[LoopBusyRefusal]: ...
async def _loop_flow_busy_reason(session, loop, agent) -> Optional[str]:
    refusal = await _loop_flow_busy_refusal(session, loop, agent)
    return refusal.reason if refusal is not None else None
```

`_loop_flow_busy_refusal` has today's body with its three returns labelled. Where
`_agents_a_loop_may_staff` returns `[]`, `held` is `BUSY_LOOP_SCOPE` if `loop.spec_document_id is None`,
else `BUSY_NO_FREE_AGENT`. That is the same predicate `_agents_a_loop_may_staff` itself uses
(`:1258`), and the archived change's D7 defines "documentless" by it. The docstring moves with the
body; the wrapper keeps a one-line docstring pointing at it.

**Why.** The route's second `_loop_has_open_task` query exists only because the guard's answer is a
bare string. Two derivations of one decision is the drift shape that module's comments record going
wrong twice (`scheduler.py:280-282`). F400 is a third instance: the route's derivation had two
outcomes, and the guard had grown a third.

**Rejected.** *Inline `loop.spec_document_id is None` in the route:* a third place that decides
"documentless", beside `_agents_a_loop_may_staff` and the guard. It would be correct today and free
to drift. *Change `_loop_flow_busy_reason`'s return type:* its other two callers (`scheduler.py:2984`,
`jobs.py:357`) want only the sentence, and a tuple there invites a caller to test it for truth and
get `True` from `("", …)`.

### D2 — One clause per condition; a flow's two sentences do not move

`run_job` maps `held` to `why`:

| `held` | Documentless loop | Flow |
|---|---|---|
| `BUSY_EMPTY_QUEUE` | `this loop's queue holds no open task` | `this loop's queue holds no open task for another agent to take` (unchanged) |
| `BUSY_LOOP_SCOPE` | `this loop's work goes only to {job.agent}, the agent its job names` | — (unreachable: a flow is never `BUSY_LOOP_SCOPE`) |
| `BUSY_NO_FREE_AGENT` | — (unreachable) | `no other agent is free to take this loop's work` (unchanged) |

The detail stays `f"{refusal.reason}, and {why}. Nothing was started."`. Measured-shape example for
the F400 case: `probe-owner is already running a turn, and this loop's work goes only to
probe-owner, the agent its job names. Nothing was started.`

**Precedence where two hold.** A documentless loop with an empty queue meets both (1) and (2). A flow
with an empty queue and nobody free meets (1) and (3). The guard asks (1) first, and the answer names
the empty queue. That is today's behaviour, pinned by
`test_run_on_a_busy_agents_empty_loop_names_the_empty_queue`, and it is the more useful sentence: the
loop lacks work, and no staffing would give it any. The spec delta states this precedence rather
than leaving it to the order of `if` statements.

**Two existing assertions move, deliberately.** `test_running_a_loop_whose_agent_is_mid_turn_answers_409_not_500`
(`test_board_agent_role.py:385`) and `test_running_a_loop_whose_agent_is_held_names_the_hold`
(`:420`) both stage a documentless loop (`_make_loop_job`, no document) with nobody else on the
roster, and both assert `"no other agent is free" in detail`. The sentence is **true** there, but it
is not the reason: freeing an agent would not change the answer. Both will assert the scope clause
instead, and assert that the roster clause is absent. Their other assertions (the busy agent, the
hold's clock, `Nothing was started`, no rows, no "already being worked") stay.

**Rejected.** *Say both "no other agent is free" and the scope where both are true:* the operator
acts on the first clause they read, and it names a remedy that does nothing. *Drop the flow's "for
another agent to take" too, for uniformity:* for a flow it explains why a free agent does not help,
which is the whole point of that sentence (design D8 of `a-task-nothing-will-move-holds-nobody`).
*Name the remedy for the scope case* ("declare a specification document to widen it"): that
turns a loop into a flow (`agent-flows:13`). It is a design choice about the loop, not a fix for a
busy turn, and the answer should not recommend it.

### D3 — Answer from a record only where this press wrote it or counted into it

Before firing, the route keeps three plain values: `earlier_run_id`, as today, and
`earlier_ticks = earlier_run.tick_count if earlier_run is not None else None`. This is an **`int`
copy**, and the comment must say why (Context, identity row). After firing:

```python
counted = (
    not wrote_row
    and latest_run is not None
    and latest_run.id == earlier_run_id
    and latest_run.tick_count != earlier_ticks
)
answered_by_row = wrote_row or counted
```

Two gates change:

- The busy-guard re-ask runs where `not answered_by_row` (today: `not wrote_row`). A counted stall
  means the guard passed at firing time and the firing reached the walk, so that row is this press's
  answer. This makes the existing scenario *"A firing that recorded its own refusal is answered from
  that record"* hold for a counted stall as it already does for a first one.
  **This gate matters only in a race.** The firing's own guard runs before the stall walk
  (`scheduler.py:2984`), so the route can meet a counted stall with a busy agent only where the agent
  became busy between the two. Task 1.9 simulates that race with a patched guard. It cannot be
  staged with real state.
- `if latest_run and latest_run.status == "skipped"` becomes
  `if latest_run is not None and answered_by_row and latest_run.status == "skipped"`. An in-flight
  decline now falls through to `_loop_in_flight_decision`, and the answer is the in-flight one:
  *"already being worked … nothing is wrong"*, or the held form where the work waits on a hold.

The requester stamp (`:1376-1381`) stays keyed on `wrote_row`. A counted row was written by an earlier
firing, and the requirement says the route *"SHALL NOT change that record's requester"*.

**Why `tick_count`, not a timestamp.** `fired_at` is deliberately not moved by a counted stall
(`scheduler.py:3228-3233`). `tick_count` is the only column a count touches, and both counting paths
(stall and plain-job coalesce) increment it.

**Rejected.** *Have `_fire_job_internal` return a richer result:* it is also the cron path's entry
point (`scheduler.py:2906`), and 18 test files call it directly. A route-local
comparison fixes the route without touching the firing. *Re-query the row in a fresh session:* that
works too, but it hides the identity trap instead of naming it, and the next edit to this code would
face the same trap.

### D4 — The requirement decides the open sentence and says "counted into"

The MODIFIED requirement:

- replaces *"This requirement does not state what the answer says … is not yet decided"* with a
  SHALL. Where the loop declares no specification document and its queue holds an open task, the
  answer SHALL say the loop gives its work only to the agent its job names, and SHALL NOT state that
  no other agent is free;
- adds the precedence (the empty queue is named where it holds), and the rule that no condition
  that did not hold is stated;
- changes *"only when the manual firing wrote that record"* to *"wrote that record or counted this
  firing into it"*;
- adds three scenarios: the documentless open-task case with a sibling free, the documentless empty
  queue, and F373's in-flight press over an earlier skipped record. It also adds an `AND` to the
  counted-stall case under the existing *"A firing that recorded its own refusal…"* scenario.

## Risks / Trade-offs

- **A concurrent cron tick can count into the row between the route's two reads.** The press's own
  firing was in flight, but the row moved, so the route answers with the stall sentence. Both firings
  ran within milliseconds against the same queue, so the stall sentence is at worst a moment stale,
  which is the pre-F373 behaviour narrowed to a race. Accepted, and noted in the code comment.
- **The documentless clause names `job.agent`.** Where the busy agent is `job.agent` (always, for this
  guard), the sentence names it twice: *"X is already running a turn, and this loop's work goes only
  to X…"*. That is deliberate. The repetition is what tells the operator that no other agent is
  involved. Open Question 2 offers a shorter form.
- **MCP callers see a changed sentence.** An agent that pattern-matched *"no other agent is free"* on
  a documentless loop sees the scope clause instead. Nothing in `hub/hub/`, `src/agentweave/`, `hub/ui/src/` or `docs/`
  contains either moved phrase except `jobs.py` itself (`grep`, R1).

## Open Questions

1. **Fold F411 in?** The app's Run button drops this answer (`JobsPage.tsx:157`). This change makes
   the answer true; F411 makes it visible. They are kept apart only because F411 rebuilds the UI
   bundle, and today's other proposal (`an-at-mention-an-agent-wrote-reads-no-file`) does too. The
   day playbook forbids two same-day proposals sharing a file. If the operator approves both for the
   same night, F411 can be a group appended to whichever is built second. That is the operator's
   call. Default: F411 stays a separate finding.
2. **Wording of the scope clause.** Proposed: *"this loop's work goes only to {agent}, the agent its
   job names"*. Shorter: *"this loop runs only {agent}"*. R2/R3 may change it; the spec pins meaning,
   not words.

## Round log

### Round 1 — 2026-09-23 (day window, D-2b)

- Picked by the day playbook's priority order: F325 (A) skipped, because it is Codex-only and
  undrivable on this machine. F400 was the next open, unproposed finding whose blast radius shares no
  file with `an-at-mention-an-agent-wrote-reads-no-file`.
- **Folded F373 in**: same branch, same requirement. Two changes editing `:1383-1453` would collide.
- **Measured** both on `dcdf723` through the real route (Context table). Answered the archived
  change's Open Question 2 by measurement: the board is right.
- **Found the identity trap** in F373's own repair sketch (Context, last row), by measuring
  rather than trusting the sketch. D3 is shaped by it.
- **Found two existing assertions** that pin the false-for-this-loop sentence
  (`test_board_agent_role.py:385`, `:420`). D2 moves them on purpose.
- **Filed F411** (the Run button shows nothing). Out of scope; Open Question 1.
- **Found the requirement's scenario *"A firing that recorded its own refusal is answered from that
  record"* untested.** No test in `hub/tests` patches the guard mid-press. Tasks 1.9 and 1.9a add it.
- Not done by R1, left for R2/R3: re-derive the decline-path table independently; check
  that no UI, doc, template or test outside `hub/tests/` matches on the moved sentences; and check the
  `agent-loops` requirement at `:793` (the busy guard's own), whose first sentence names only two
  of the three conditions, for whether this delta must touch it too.
