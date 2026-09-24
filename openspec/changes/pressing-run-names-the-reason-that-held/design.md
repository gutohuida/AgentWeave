# Design — pressing Run names the reason that held

## Operator review, 2026-09-24

An Opus adversarial review (`spec-queue/tracks/reviews/2026-09-23-changes-2026-09-24.md` §2) found
**APPROVE WITH FIXES**. The operator approved this change with its defaults:

- **F411, F412 and F413 stay separate findings** (Open Questions 1, 3 and 4). None is folded in.
- **The proposed scope-clause wording stands** (Open Question 2): *"this loop's work goes only to
  {agent}, the agent its job names"*.

These fixes from the review are applied here:

- **MEDIUM, D3 contradicted itself on the re-ask gate.** The *"Two gates change"* bullet said the busy
  re-ask runs where `not answered_by_row`. Task 1.14 has a concurrent tick's `in_progress` row, so
  `wrote_row` is true, and it expects the busy 409. That gate would skip the re-ask and answer 500,
  which is today's bug. The wording is deleted. The re-ask is now **unconditional below the `skipped`
  and `failed` arms**, which already return first. That matches the sketch, task 2.3 and tasks 1.9
  and 1.14 (D3).
- **LOW, a stale-409-to-500 race** is now listed under Risks.
- **LOW, stale line citations.** They are refreshed against HEAD `8bc926f`, and function names are
  used where possible. The round log keeps the citations each round actually read.
- **LOW, coordination with two other changes' declared rebases** (`an-agent-can-be-paused-and-keeps-its-input`
  task 1.7, and `run-id-in-an-event-always-names-a-run`) is now listed under Risks.

**Round 1, 2026-09-23** (day window, D-2b). F400 and F373, re-measured on `dcdf723` with
`scripts/drive/d2b_0923_run_answer_probe.py`. To re-run it, copy it under `hub/tests/` as
`test_zz_probe_*.py` and run it with `-s`. It prints what the route answers and asserts nothing about
the right answer. **Nothing here is implemented yet.**

## Context

`run_job` (`hub/hub/api/v1/jobs.py`, `:1372-1510` at HEAD `8bc926f`) fires the job through the
scheduler with the route's own session: `scheduler._fire_job_internal(job, trigger="manual",
session=session)`, at `:1417`. When that returns `False`, the `if not success:` branch (`:1428-1497`)
turns the decline into an HTTP answer. It cannot ask the firing why, because several declines
deliberately write nothing. Every `return False` in `_do_fire_job` (which `_fire_job_internal`
wraps), read in R1. The line column gives each branch's `return` at HEAD `8bc926f`:

| Path | Line | Writes a `JobRun`? | What the route answers today |
|---|---|---|---|
| Busy guard (`_loop_flow_busy_reason`) | `:3059` | **no** | Re-asks the guard: `{busy}, and {why}. Nothing was started.` (409) |
| Agent skip (`_job_agent_skip_reason`) | `:3098` | yes, `skipped` | That row's reason (409) |
| Plain job held, first firing | `:3140` | yes, `skipped` | That row's reason (409) |
| Plain job held, later firings | `:3121` | **no**, counts `tick_count` into the newest row | That row's reason (409), correctly |
| Loop stop reached | `:3216` | yes, `skipped` | That row's reason (409) |
| In flight (`DECISION_IN_FLIGHT`, F23) | `:3269` | **no** | **The newest row's reason if it is `skipped` (F373)**, else the in-flight answer |
| Stall, first firing | `:3325` | yes, `skipped` | That row's reason (409) |
| Stall continues (D6 of `loop-notices-and-reacts`) | `:3303` | **no**, counts `tick_count` | That row's reason (409), correctly |
| Exception before `run` exists (R2) | caught by the single `except` (`:3514`) | **no**: `if "run" in locals()` (`:3518`) is false | **The newest row's reason if it is `skipped`** (measured, R2), else 500 `Failed to fire job` |
| Exception after `run` exists | same `except`, `return False` at `:3537` | yes, `failed` | **Re-decides first**: the in-flight answer where `_loop_in_flight_decision` finds the queue in flight (measured, R2), else 500 with its summary |
| Exception after `run` was **discarded** (R3): the in-flight and counted-stall branches discard and commit, then emit the staged loop edit (`_emit_loop_edit_applied`, `:3264`, `:3298`) | same `except` | **no**: `run` is still a local, so the `except` persists `job_run_failed` naming a run id that no longer exists | The decision the firing made (measured, R3: the in-flight answer) |

R2 rebuilt this table from `grep "return False\|return True"` over `_do_fire_job` before reading R1's,
and agreed on nine rows. It found the two exception rows' behaviour R1 did not list: `_do_fire_job`
has one `try`, and its `except` marks a row `failed` only when the row already exists.

The route tells "this press wrote the row" apart from "an earlier firing wrote it" by comparing the
newest row's **id** before and after (D11 of `a-spent-allowance-holds-the-queue`, `jobs.py:1409-1420`). A
counted stall keeps the id, so by id it looks exactly like a decline that wrote nothing. The
`skipped` branch (`jobs.py:1455-1459`) is therefore left ungated. It is right for the two counting paths
and wrong for the in-flight one, which is F373.

**The busy guard** (`_loop_flow_busy_reason`, `scheduler.py:335-375`) refuses when the job's agent is running or held **and**
one of three things holds. It asks them in this order:

1. The loop holds no non-terminal task (`_loop_has_open_task`, `:318-332`).
2. The loop declares no specification document. `_agents_a_loop_may_staff` returns `[]` for it
   (`scheduler.py:1263-1284`), so the pool is empty whoever is free.
3. The loop is a flow and `_agents_that_are_free` is empty.

It returns only the busy sentence. The route then re-derives which half held with a second
`_loop_has_open_task` query (`jobs.py:1439-1449`), and it can tell only (1) from not-(1). It files (2) under
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
| **R2** documentless loop, owner idle, `session_mode="resume"`, the resume lookup raises, an hour-old `skipped` row | 409 `loop queue is stalled: 1 still awaiting a prerequisite's approval`. No row written. **False**: the firing crashed, and the answer is an earlier firing's stall, as a conflict |
| **R2** documentless loop, owner idle, the turn starts and a later step raises (`schedule_agent` patched to start a `Run`, then raise) | 409 `Every task on this loop's queue is already being worked. Nothing was started, and nothing is wrong…` over the row **this press wrote**, which reads `failed` / `r2 probe: failed after the turn started`. **False** |
| **R2** `schedule_agent` returns `terminal_failure` | 200 `{"success": true}` over a row reading `failed`. **Out of scope**: the firing returns `True` (F412, Open Question 3) |
| **R3** F373's flow (work in flight, a sibling free), no earlier row, the resume lookup raises | 409 *"already being worked … nothing is wrong"*. No row, no `job_run_failed`. **False, and D3 does not change it** (D3, *What D3 cannot see*; F413) |
| **R3** documentless loop, owner mid-turn, the resume lookup raises (before the firing's own guard) | 409 with the busy sentence. No row, no event. The route's re-ask is the first time the guard is asked at all |
| **R3** F373's flow with a staged loop edit whose audit emit raises (after the in-flight branch discarded `run`) | 409 *"already being worked … nothing is wrong"*. No row, but a `job_run_failed` event naming `run-a0d474043a0d`, which does not exist (F413) |

The **identity** row is the constraint on D3. The session factory is `expire_on_commit=False`
(`db/engine.py:163`), and `_stall_run_to_increment` returns the identity-mapped instance the route
already holds. The route's `earlier_run` object **is** the counted row. So F373's ledger sketch,
*"read the newest row's `tick_count` together with its id"*, works only if the value is copied out
before the firing. Comparing `latest_run.tick_count` with `earlier_run.tick_count` afterwards
compares an object with itself and always reads "unchanged".

**The board is already right** (archived design's Open Question 2, answered). For the documentless
open-task case, `decide_firing` answers `stalled` with `loop queue is stalled: no claimable task
among 1 open (1 pending)` (`_stall_reason_from_walk`, `scheduler.py:2243`). The board's re-ask (`jobs.py:389`)
replaces that with the busy sentence, and the probe read `probe-owner is already running a turn`
on the board. The busy sentence alone names no roster, so it is true. The board needs no edit here.

**Who reads the route's answer.** The MCP tool `run_job` (`mcp_server.py:929-937`), which returns
the Hub's answer to the calling agent, and any API client. **The app's own Run button does not
display it** (`hub/ui/src/components/jobs/JobsPage.tsx:157`, `onRun={runJob.mutate}`, no `onError`; filed as F411, Open Question 1).

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
    reason: str      # `_loop_agent_busy_reason`'s sentence, unchanged
    condition: str   # one of the three constants above


async def _loop_flow_busy_refusal(session, loop, agent) -> Optional[LoopBusyRefusal]: ...
async def _loop_flow_busy_reason(session, loop, agent) -> Optional[str]:
    refusal = await _loop_flow_busy_refusal(session, loop, agent)
    return refusal.reason if refusal is not None else None
```

`_loop_flow_busy_refusal` has today's body with its three returns labelled. Where
`_agents_a_loop_may_staff` returns `[]`, `condition` is `BUSY_LOOP_SCOPE` if `loop.spec_document_id is None`,
else `BUSY_NO_FREE_AGENT`. **Not `held`** (R1's name, renamed by R2): in this module *held* means a
provider-allowance hold (`provider_hold`, `held_agents`), and the guard itself refuses a held
agent, so `refusal.held == BUSY_EMPTY_QUEUE` would read as a statement about a hold. That is the same predicate `_agents_a_loop_may_staff` itself uses
(`_agents_a_loop_may_staff`, `scheduler.py:1281`), and the archived change's D7 defines "documentless" by it. The docstring moves with the
body; the wrapper keeps a one-line docstring pointing at it.

**Why.** The route's second `_loop_has_open_task` query exists only because the guard's answer is a
bare string. Two derivations of one decision is the drift shape that module's comments record going
wrong twice (`_running_agents`' docstring, `scheduler.py:303-305`). F400 is a third instance: the route's derivation had two
outcomes, and the guard had grown a third.

**Rejected.** *Inline `loop.spec_document_id is None` in the route:* a third place that decides
"documentless", beside `_agents_a_loop_may_staff` and the guard. It would be correct today and free
to drift. *Change `_loop_flow_busy_reason`'s return type:* its other two callers (the firing, in `_do_fire_job`, `scheduler.py:3045`,
and the board's re-ask, `jobs.py:389`) want only the sentence, and a tuple there invites a caller to test it for truth and
get `True` from `("", …)`.

### D2 — One clause per condition; a flow's two sentences do not move

`run_job` maps `condition` to `why`:

| `condition` | Documentless loop | Flow |
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

**R3: the precedence is a total order.** A documentless loop whose roster is also empty meets (2) and
(3), and neither is the empty queue, so R2's *"name the empty queue alone"* says nothing about it. The
scope paragraph settled it (*"even where the roster is in fact empty"*), but only by a second
sentence elsewhere. The delta now states one order, the guard's own: the empty queue, then the
loop's scope, then the roster. The answer names only the first that holds. For a documentless loop
(3) is never even evaluated, because `_agents_a_loop_may_staff` returns `[]` before asking who is
free (`_agents_a_loop_may_staff`, `scheduler.py:1281-1282`).

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

**R2: the row this press wrote is its answer, whatever its status.** `wrote_row` with `success` false
means the row reads `skipped` or `failed`: every path that writes and declines sets one of the two
(Context table). Today only `skipped` is read off the row. A `failed` row falls through to
`_loop_in_flight_decision`, which re-decides the loop *after* the failure and, measured, answers
*"already being worked … nothing is wrong"* over a firing that crashed after its turn started.
So the branch becomes:

```python
if answered_by_row and latest_run.status == "skipped":
    raise HTTPException(409, detail=latest_run.error_summary or "Job was skipped.")
if answered_by_row and latest_run.status == "failed":
    raise HTTPException(500, detail=latest_run.error_summary or "Failed to fire job")
# Below here the press wrote nothing and counted into nothing (or the row is not a decline's; R3).
loop = await _job_loop(session, job)
...busy re-ask, then the in-flight answers, then 500 "Failed to fire job"
```

A counted row is always `skipped` (`_stall_run_to_increment` matches only `skipped`, `scheduler.py:1001`), so the
`failed` arm is reached only through `wrote_row`.

**R3: each status is named; no `else`.** R2's sketch answered 500 for any status other than
`skipped`. That is right only if the row really is the press's. The Risks section already accepts
that `wrote_row` can be true for a concurrent cron tick's row, and a tick that fired writes
`in_progress`. R2's `else` would answer that press *"Failed to fire job"*, the alarming answer, for a
tick that started work. The press itself declined, and wrote nothing, so the fall-through is its true
answer. Today's code reaches the same 500 by another route: `wrote_row` skips the re-ask, and the
in-flight decision finds nothing. Measured (R3, probe `test_r3_a_concurrent_ticks_row_is_not_a_failure`):
a documentless loop, owner mid-turn, and a firing patched to write a tick's `in_progress` row and
return `False`. The route answered **500 `Failed to fire job`**. The press's true answer is the busy
guard's 409. So task 1.14 fails today as well. The final 500 no longer reads
`latest_run.error_summary`: below the gate there is no row of this press's to read, and the existing
`if … wrote_row …` guard on it becomes dead. Where the press wrote nothing and nothing refuses or is
in flight, the firing raised before its row existed (Context, R2 rows), and *"Failed to fire job"* is
the true answer; the exception is in the Hub's log, which is where `_do_fire_job` sends it.

Two gates change:

- **The busy-guard re-ask is unconditional below the `skipped` and `failed` arms** (today it is gated
  on `not wrote_row`). *Operator review, 2026-09-24:* R1-R3 worded this as *"where `not
  answered_by_row`"*, which contradicted the sketch above, task 2.3 and task 1.14, and that wording is
  deleted. No gate is needed. A row this press wrote or counted into reads `skipped` or `failed`, and
  those two arms return before the re-ask is reached. Any other row status falls through to the
  re-ask, and that includes a concurrent tick's `in_progress` row. With a `not answered_by_row` gate,
  task 1.14's press (`wrote_row` true through the tick's row) would skip the re-ask, find nothing in
  flight, and answer 500 *"Failed to fire job"*. That is today's bug, kept. Unconditional, it answers
  the busy 409.
  A counted stall is answered by the `skipped` arm, before the re-ask. It means the guard passed at
  firing time and the firing reached the walk, so that row is this press's answer. This makes the
  existing scenario *"A firing that recorded its own refusal is answered from that record"* hold for
  a counted stall as it already does for a first one.
  **The ordering matters only in a race.** The firing's own guard runs before the stall walk (in
  `_do_fire_job`, `scheduler.py:3045`), so the route can meet a counted stall with a busy agent only
  where the agent became busy between the two. Task 1.9 simulates that race with a patched guard. It
  cannot be staged with real state.
- The row is read only where `answered_by_row` (the block above). An in-flight decline now falls
  through to `_loop_in_flight_decision`, and the answer is the in-flight one: *"already being worked
  … nothing is wrong"*, or the held form where the work waits on a hold. A firing that raised before
  its row existed falls through all three and answers 500 *"Failed to fire job"*, not an earlier
  firing's stall.
- `_loop_in_flight_decision` is asked only below the `skipped` and `failed` arms, where the press
  wrote nothing it can answer from. It is never asked to explain a decline's row this press wrote.

The requester stamp (`jobs.py:1422-1426`) stays keyed on `wrote_row`. A counted row was written by an earlier
firing, and the requirement says the route *"SHALL NOT change that record's requester"*.

**What D3 cannot see (R3, measured, F413).** The route reads side effects. A firing that raised and
left no row looks exactly like a healthy decline that also left none. There are two ways this
happens: the firing raised before `run` existed, or it raised after the in-flight or counted-stall
branch had discarded `run`. Below the two arms the route re-decides the loop, as the requirement says it
must where nothing was written. So the crash is answered as the decision the firing would have made.
That is 409 *"already being worked … nothing is wrong"* on an in-flight flow, and the busy sentence
on a busy loop. On the busy loop that answer is true of the loop. On the in-flight flow, *"nothing is
wrong"* is not true. The route cannot repair this, because no fact about the crash reaches it.

The repair belongs in the firing: every failed firing leaves a `failed` row. D3 is what makes that
repair enough. Once the row exists, *"the row this press wrote is its answer, whatever its status"*
answers all three R3 cases as 500 with their reason, and the route needs no further edit. That repair
moves what the firing writes, and on the cron path too, which this change's non-goals exclude. So it
is Open Question 4.

*Rejected again (R3 re-checked R1's reason):* having the firing return why it declined would let
the route see the crash. But 18 test files assert `_fire_job_internal(...) is False` / `is True`
(`grep`), so any richer return is a sweep through them.

**Why `tick_count`, not a timestamp.** `fired_at` is deliberately not moved by a counted stall
(`_do_fire_job`'s continuing-stall branch, `scheduler.py:3289-3292`). `tick_count` is the only column a count touches, and both counting paths
(stall and plain-job coalesce) increment it.

**Rejected.** *Have `_fire_job_internal` return a richer result:* it is also the cron path's entry
point (`scheduler.py:2969`), and 18 test files call it directly. A route-local
comparison fixes the route without touching the firing. *Re-query the row in a fresh session:* that
works too, but it hides the identity trap instead of naming it, and the next edit to this code would
face the same trap.

### D4 — The requirement decides the open sentence and says "counted into"

The MODIFIED requirement:

- replaces *"This requirement does not state what the answer says … is not yet decided"* with a
  SHALL. Where the loop declares no specification document and its queue holds an open task, the
  answer SHALL say the loop gives its work only to the agent its job names, and SHALL NOT state that
  no other agent is free;
- adds the precedence (the empty queue is named where it holds; R3 made it a total order: the
  empty queue, then the loop's scope, then the roster), and the rule that no condition that did not
  hold is stated;
- changes *"only when the manual firing wrote that record"* to *"wrote that record or counted this
  firing into it"*;
- adds three scenarios: the documentless open-task case with a sibling free, the documentless empty
  queue, and F373's in-flight press over an earlier skipped record. It also adds an `AND` to the
  counted-stall case under the existing *"A firing that recorded its own refusal…"* scenario.
- **R2 adds** a paragraph and two scenarios: a firing that recorded a failure is answered as a
  failure carrying its reason, never as work in flight; a firing that recorded nothing and was
  neither refused nor in flight is answered as a failure to fire, never with an earlier firing's
  reason.

**R2: `agent-loops:793` does not join the delta.** Its first sentence names two of the guard's three
conditions, and its fifth paragraph states the third (the empty queue) as its own SHALL. Together
they state the guard completely, and this change moves no decision the guard makes. The sentence the
operator reads is governed at `:1499`, which this delta rewrites.

## Risks / Trade-offs

- **A concurrent cron tick can count into the row between the route's two reads.** The press's own
  firing was in flight, but the row moved, so the route answers with the stall sentence. Both firings
  ran within milliseconds against the same queue, so the stall sentence is at worst a moment stale,
  which is the pre-F373 behaviour narrowed to a race. Accepted, and noted in the code comment.
- **The documentless clause names `job.agent`.** Where the busy agent is `job.agent` (always, for this
  guard), the sentence names it twice: *"X is already running a turn, and this loop's work goes only
  to X…"*. That is deliberate. The repetition is what tells the operator that no other agent is
  involved. Open Question 2 offers a shorter form.
- **`wrote_row` can be a concurrent tick's row (R2).** A cron firing that writes a row between the
  route's two reads makes `wrote_row` true for a press that wrote nothing, and the route answers
  from the tick's row. This is today's behaviour, unchanged, and narrower than F373: both firings ran
  within milliseconds against the same queue. D3 does not make it worse; `failed` rows are read the
  same way `skipped` ones already are.
- **A crash that leaves no row is still answered as a decline (R3, F413).** See D3, *What D3 cannot
  see*. The answer on an in-flight flow stays *"nothing is wrong"* after this change. That is not a
  regression, since it is today's answer too. The spec delta does not promise otherwise: its failure
  paragraph applies only where *"the guard does not refuse, and the queue is not in flight"*.
- **Plain jobs move too (R2).** The gate is not loop-specific. A plain job whose firing raised before
  its row existed, after an earlier coalesced `skipped` row, answered 409 with the coalesce reason;
  it will answer 500 *"Failed to fire job"*. A plain job's counted coalesce is still answered from
  its row, because `counted` covers it.
- **An in-flight firing whose work finishes before the route re-asks now answers 500, not a stale
  409 (Operator review, 2026-09-24).** The firing decides `DECISION_IN_FLIGHT` and writes nothing.
  Then the task it saw in flight finishes before the route calls `_loop_in_flight_decision`, which
  returns `None`. Today, with an earlier `skipped` row, the ungated `skipped` branch answers that
  earlier row's stall reason, a stale 409. After this change the row is not the press's, the re-ask
  finds no busy agent, the in-flight decision finds nothing, and the route answers 500 *"Failed to
  fire job"*. The answer is false either way. The 500 is more alarming, but it no longer names an
  earlier firing's condition as this press's. The window is the milliseconds between the firing's
  decision and the route's re-decision. Accepted, and the code comment on the final 500 names it.
- **Coordination with two other changes' declared rebases (Operator review, 2026-09-24).** Both
  touch `run_job`. Whichever lands second rebases onto the first:
  - `an-agent-can-be-paused-and-keeps-its-input`, task 1.7, asserts only `409` and `is paused` for a
    paused loop agent, and not the sentence around it, because this change reshapes that sentence.
    Its design records the overlap as textual adjacency in `run_job`, not a semantic conflict. The
    pause is read inside the busy guard's `_loop_agent_busy_reason`, which
    `_loop_flow_busy_refusal` keeps calling (D1), so `refusal.reason` carries the pause sentence
    unchanged. If that change lands first, re-run task 1.11's controls and that change's 1.7 after
    group 2.
  - `run-id-in-an-event-always-names-a-run` edits `run_job`'s success return (`jobs.py:1510`) and
    `_record_job_run_failure`'s payload. It renames the route's local `run_id` to `job_run_id`, which
    sits next to this change's `wrote_row` and requester-stamp lines (`jobs.py:1419-1426`). This
    change edits only the `if not success:` branch and the `earlier_ticks` copy before the firing, so
    the overlap is textual. Its proposal already says *"Land either first; the second rebases."*
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

3. **Fold F412 in?** (filed by R2, measured). When `schedule_agent` reports that no turn began
   (`terminal_failure`), `_do_fire_job` marks its row `failed` (`scheduler.py:3472-3478`) and still
   returns `True`, so `run_job` answers `200 {"success": true}`. It is F108's open class, on this
   route. It stays out because `terminal_failure` has known dishonest defaults (F108's section: six
   early returns claim it without meaning it), so reading it here needs its own look at which
   reasons are really terminal, and because it changes the success branch, which this change does
   not touch. Default: separate finding.
4. **Fold F413 in?** (filed by R3, measured). A firing that raises and leaves no row is answered as
   the decision it would have made (D3, *What D3 cannot see*). Making the `except` always leave a
   `failed` row closes it, and D3 then answers it with no further route edit. It stays out because
   it changes what the firing writes, on the cron path as well as the route. A crash that recurs
   every tick needs its own answer against `_prune_job_history`'s window. Default: separate finding.
   If the operator folds it in, it is a new group between 2 and 3, and it needs its own spec
   paragraph, since the delta today scopes the failure answer to *"not in flight"*.

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

### Round 2 — 2026-09-23 (day window, D-3b)

- **Rebuilt the decline table from `grep` before reading R1's.** Agreed on nine rows and their line
  ranges. Found two R1 did not describe: an exception **before** the row exists writes nothing (the
  `except` guards on `"run" in locals()`), and an exception **after** it writes `failed` but is then
  re-decided by `_loop_in_flight_decision`. Both measured through the route (Context, R2 rows): the
  first answered an hour-old stall as a 409, the second answered *"already being worked … nothing is
  wrong"* over the `failed` row the press itself wrote.
- **D3 widened**: the row the press wrote is its answer whatever its status (`skipped` → 409,
  `failed` → 500), and the in-flight re-decision is asked only where the press wrote nothing. This is
  the argument D3 already made for `skipped`, applied to the other status a declining write can have.
  Tasks 1.12, 1.13 and 2.3; spec delta paragraph and two scenarios.
- **Re-ran R1's probe** on `0beef69`: all seven cases reproduce exactly (F400's two false clauses, the
  flow control, F373's stale stall, the continuing stall, and the identity trap,
  `same_object=True snapshot=1 earlier_now=2`). Three R2 cases added to the probe.
- **Renamed `LoopBusyRefusal.held` → `condition`**: *held* is this module's word for a provider hold.
- **Made two assertions non-vacuous.** An operator's press sends no run identity, so R1's *"the
  earlier row's requester is unchanged"* (tasks 1.7, 1.8) compared `None` with `None`. Measured: a
  seeded `run-r2-sentinel` survives a counted stall. The tasks now seed one.
- **Checked `agent-loops:793`**: no delta needed (D4).
- **Tightened the precedence**: where two conditions hold the answer names the empty queue *alone*;
  R1's "SHALL name the empty queue" did not forbid naming the scope beside it.
- **Checked R1's other claims**: 18 test files call `_fire_job_internal` (`grep -l`);
  `test_board_agent_role.py:385`/`:420` stage documentless loops and pin the roster clause;
  `test_a_task_nothing_will_move_holds_nobody.py:454` stages a flow and is unaffected; `:574` stages a
  documentless empty queue and pins only an absence, so it keeps passing (task 1.3 adds the new
  assertion). No file under `hub/hub/` except `jobs.py`, nor `hub/ui/src/`, `src/` or `docs/`,
  contains either moved phrase. The board's re-ask (`jobs.py:357`) still reads only the sentence.
- **Filed F412 (B)**: a terminal schedule failure answers Run with `200 {"success": true}`. Open
  Question 3.

### Round 3 — 2026-09-23 (day window, D-4b)

- **Re-derived from the code before opening R2's notes.** Read `run_job` (`jobs.py:1326-1464`) and
  `_do_fire_job` (`scheduler.py:2926-3465`) and listed every way out: four declines that write
  nothing or count, four that write `skipped`, the success path (including F412's `failed` row), and
  the single `except`. This agreed with R2's table on all ten rows. It found an eleventh: an
  exception **after** `run` was discarded. The in-flight and counted-stall branches discard `run`,
  commit, and then emit the staged loop edit. If that raises, `"run" in locals()` is still true.
- **Measured three R3 cases** (probe, `test_r3_*`). A crash before the row on an in-flight flow
  answers *"already being worked … nothing is wrong"*. A crash before the row on a busy loop answers
  the busy sentence, although the firing never reached its own guard. A crash after the discard
  answers *"nothing is wrong"*, and it persists a `job_run_failed` event naming `run-a0d474043a0d`,
  a run that does not exist. **D3 changes none of these.** The route cannot tell a crash that left
  no row from a decline that left none. Filed **F413 (B)**, and D3 now names the gap (*What D3
  cannot see*). Open Question 4 offers folding F413 in. It is kept out because the repair is in the
  firing, on the cron path too.
- **D3's `else → 500` replaced by named statuses.** R2's sketch answered 500 for any status other
  than `skipped`. `wrote_row` is true for a concurrent tick's row, as R2's own Risks entry says, and a
  tick that fired writes `in_progress`. Measured (`test_r3_a_concurrent_ticks_row_is_not_a_failure`):
  today the route answers **500 `Failed to fire job`** to a press the busy guard refused. Task 1.14
  added. Task 2.3 updated.
- **Precedence made a total order** (D2, spec delta). *"Name the empty queue alone"* said nothing
  about a documentless loop with an empty roster, where neither of the conditions that hold is the
  empty queue.
- **Checked the existing tests that pin `run_job`'s answers** (`grep "Failed to fire job"`, and
  `== 500` over every test that posts `/run`). None asserts a 500 from the `not success` branch.
  `test_a_review_nobody_is_doing.py:605` asserts its absence: a first stall writes its row, so D3
  answers from it, unchanged. `test_board_agent_role.py:297` is the in-flight case with no earlier
  row, which is also unchanged. The success-path tests (`test_jobs.py:412`, `test_jobs_crud.py:400`,
  `:538`) are untouched by a `not success` edit. So groups 1 and 2 move no assertion beyond task
  1.6's two.
- **Checked R1's rejection of a richer return.** It still holds: the test files assert
  `_fire_job_internal(...) is False` / `is True`.
- **Task 1.9's patch** reaches the route only while `run_job` imports `_loop_flow_busy_refusal`
  inside the function, as it imports the guard today. Task 2.2 now says so. A module-level import
  would bind the unpatched function.
- **Re-ran the whole probe on `dfd5b29`.** R1's seven cases and R2's three reproduce exactly. That
  includes the identity trap (`same_object=True snapshot=1 earlier_now=2`) and F412's 200.
