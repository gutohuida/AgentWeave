## Why

A task sitting in `under_review` under an agent that is not reviewing it is invisible to every
operator surface, and the surface that speaks says the opposite of the truth. Pressing Run on such a
loop answers `409 "Every task on this loop's queue is already being worked. Nothing was started, and
nothing is wrong — the next firing picks up whatever finishes."` while both agents are idle, no run
is live and `stall_reason` is `null`. Nothing finishes, so the sentence's promise can never come
true. Reproduced live twice during flow drives (F154, severity A), then deterministically with no
agent turn at all — `scripts/drive/t_f154_wedged_review.py`, **16/16 against `master` at `d546a8f`**.

**One of F154's claims does not survive round 1, and it sharpens the rest.** The finding reads
`agent_capacity: "held"` on an idle agent as part of the defect, and it is not: `held` is the
correct value and was split out of `working` for exactly this case — *"a review that ended without a
verdict, or whose turn failed"* (`hub/hub/schemas/jobs.py:136-143`, finding F63). The board already
distinguishes what the firing does not. So the product holds two versions of one fact: the firing
decides on `task.assignee` and the board repairs the same fact afterwards for display, from the runs
table. The acting half has the wrong version, and `task_attribution`'s own docstring says what that
collection is not — *"**Not** 'is running' — that is the confusion this whole module exists to
end"* (`task_attribution.py:132-134`).

This is a breach of two shipped requirements, not a gap:

- `agent-flows` already requires *"the operator is told which declared reviewer gave no verdict,
  naming the task"*, and that an availability-picked reviewer that gave no verdict is replaced.
  `run_divergence._answer_failed_review` (`run_divergence.py:377-446`) implements both correctly.
- `agent-loops:815` defines a stalled queue as one that *"holds tasks that are not terminal and none
  of them is claimable"* and requires the refusal to *"record a reason naming what the queue is
  waiting on"*. This queue qualifies exactly, and records `stall_reason: null`.

The defect is one line of classification. `decide_firing`'s `WITH_REVIEWER` branch
(`scheduler.py:1355-1361`) appends the task to `in_flight` on the strength of `task.assignee` alone.
It never consults `held`, the per-task *"is a turn actually running on this"* map it computed three
lines earlier at `scheduler.py:1291` and which the ordinary-work arm next door does consult. So a
review whose reviewer is mid-turn and a review whose reviewer went home are the same row to it, and
`DECISION_IN_FLIGHT` — defined at `scheduler.py:938-947` as *"every candidate is already being
worked by an agent mid-turn"* — is claimed for a task nobody is working.

Two distinct populations reach this row, and only one of them has ever had a run to diagnose:

1. **A review turn ended without a verdict.** The run boundary fires, `_answer_failed_review` runs,
   and on the branch where nobody is left to substitute it correctly *surfaces* — leaving the task
   `under_review` with the silent reviewer still in `assignee`. The corpus's remedy worked, and the
   loop's own surfaces still say nothing is wrong.
2. **The operator walked the task to `under_review` by hand**, which is the only route the lifecycle
   offers them. No run ever existed, so no boundary ever fired and no scenario in the corpus covers
   it. This is the population the reproduction builds, and it needs no model, no flake and no
   crash.

Both end at the same false sentence, and one predicate covers both.

## What Changes

- `decide_firing` stops treating a non-empty cannot-staff collection as proof that work is in
  flight. `DECISION_IN_FLIGHT` is chosen only where at least one of those tasks actually has a turn
  behind it; otherwise the firing falls through to the stall path with a sentence naming the task
  and the agent whose name is on it, reaching `stall_reason` through the F64 rule already in place
  at `scheduler.py:1590-1609` and the operator through `_emit_review_unstaffed`.
- The task **stays** in `_cannot_staff`. That collection has exactly two consumers
  (`scheduler.py:2611`'s log line and `task_attribution.staffing_from_decision`), and the second is
  what makes the board say `held` rather than `assigned`. Removing the row to express the fix would
  silently undo F63 — a real cost hidden behind an apparently tidier repair, and the reason this
  change touches the *decision* rather than the collection.
- The predicate is **not** `task.assignee is not None`, and **not** `held` alone. It is: a running
  turn bound to the task, **or** an undelivered inbound queue entry naming the task — because
  `schedule_agent` (`turn_scheduler.py:78-105`) can leave a staffed review durably queued rather
  than running (`waiting_reason="agent is already running"`, an exhausted hop budget or token
  budget), and a review waiting its turn in the queue is attended, not abandoned.
- `review_unstaffed` is emitted when the fact is new or changed for a task rather than on every
  tick. This change is what makes that population permanent — it cannot clear without the operator —
  so at a five-minute tick the unchanged fact would otherwise bury the activity log, which is the
  harm `agent-loops`' "records only what is new" already names. Affects the existing rung-3
  population the same way, deliberately.
- `agent-loops` gains the statement the code's own constant already makes in its docstring and does
  not keep: a task counted as in flight is one an agent is working, and a queue whose only
  non-terminal work is a review nobody is doing is stalled, with a reason naming it.
- `agent-flows` gains the population its existing no-verdict scenarios cannot reach: a review with a
  named reviewer and no turn behind it, however it got there, including with no run in its history
  at all.
- No new machinery. `held` is already computed on this walk, `unstaffed` is already carried out of
  it, and both the stall sentence and the event already exist.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-loops`: "in flight" is constrained to mean a turn is actually running; a queue whose only
  non-terminal task is a review nobody is doing is stalled and names it, rather than being reported
  as busy.
- `agent-flows`: the existing no-verdict surfacing is extended to a review nobody is doing whatever
  its history — including a task with no run ever bound to it — and is required to reach the loop's
  own state surface, not only the event stream.

## Impact

- `hub/hub/scheduler.py` — the `WITH_REVIEWER` branch, and one new predicate near
  `tasks_held_by_a_running_turn`'s call site.
- `hub/hub/run_task_binding.py` — most likely home for the predicate, beside
  `tasks_held_by_a_running_turn` (`:267-295`) whose map it extends. To be settled in design.
- `GET /api/v1/projects/{id}/loops/{id}` — `stall_reason` stops being `null` for this row.
  `current_tasks[].agent_capacity` is already correct and SHALL keep reading `held`; a change that
  moves it to `assigned` has broken F63, whatever else it fixed.
- `POST /jobs/{id}/run` — the 409 sentence for this population changes from "nothing is wrong" to a
  sentence naming the task and the agent whose name is on it.
- No database migration, no new column, no API shape change.

## Non-Goals

- **Re-staffing the review automatically.** `agent-flows` requires a declared reviewer be surfaced
  and never substituted, and `_answer_failed_review` already re-resolves the availability-picked
  case at the run boundary. This change makes the wedge *visible*; it does not add a second
  re-staffing path, and it must not, or the two would disagree.
- **F167.** `agents_that_worked` reads `TaskTransition.actor_agent`, which is NULL for every edge an
  operator walked by hand, so F70's author recovery cannot recognise an author whose history is
  entirely the operator's. This change names that row's wedge too, because its predicate does not
  ask who the assignee is — but it does not repair the recovery's blindness, and F167 stays open.
- **The reviewer harness failure.** Two of three live drives had a reviewer loop on `ToolSearch` and
  never deliver the verdict it had reached. That is the spawned Claude CLI presenting the MCP tools
  as deferred, it is not the Hub's, and the Hub should not try to prevent it.
- **Changing `under_review`'s exits.** The operator's rescue already works and is one transition
  (`t_f154_wedged_review.py` LANE 4). The defect is that they are never told they need it.
- **The `DECISION_IN_FLIGHT` ordering fix from F23.** The `in_flight` branch stays above the stall
  check. A genuinely busy flow must still not call itself stalled.
