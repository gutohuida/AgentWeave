# A review started by hand can finish

## Why

One operation — *review this task* — has two dispatch paths, and only one of them leaves the
reviewer able to finish.

The **flow path** staffs the task before the turn. `scheduler.py`'s `_do_fire_job` and
`_stage_selection` both call `_enter_selected_task`, which writes `task.assignee = agent` and
applies `completed -> under_review`, in that order and inside one transaction. The ordering is
deliberate and is F70's fix: `_guard_reviewer_is_not_the_author` refuses `-> under_review` while
the task still names the agent that completed it, which is exactly what `assignee` holds at that
moment.

The **manual path** — `POST /agent/trigger {"review_task_id": …}` — validates that a commit exists
to review, provisions the reviewer's detached checkout through `review_turn.prepare_review_turn`,
and staffs nothing. `run_task_binding.task_named_by` treats `review_task_id` as *check out this
commit*, explicitly not as ownership, and no other step fills the gap.

So a reviewer dispatched by hand does the work and then finds every exit closed. Measured live
(finding F76, severity A, 2026-08-27), the agent tried four and was refused four times:

| It tried | It got |
|---|---|
| `update_task` to `approved` | 409 — from `completed` the only transition is `under_review` |
| `update_task` to `under_review` | 403 — the task is still assigned to its author |
| `record_evidence` | 409 duplicate (F75) |
| `send_message` to `Operator` | 404 — the operator is not on the roster (F77) |

Every one of those refusals is individually correct, and the `under_review` one is the best refusal
in the product: it names the problem, offers two remedies, and states the cost of doing nothing.
The defect is not in any of them. It is that the composition has no exit, and that the operator
pays for a full review turn to discover it — the verdict existed only in the chat transcript.

The corpus does not currently forbid this. `task-lifecycle-governance` requires that *a review a
flow cannot staff is not reported as staffed*, which binds the flow path and says nothing about the
manual one. `run-task-binding` requires that *a run started to review a task binds to that task*
and, correctly, that binding changes no status. Nothing anywhere requires that dispatching a review
leaves the reviewer able to record one. That silence is what let the two paths diverge.

## What Changes

- **Dispatching a review staffs the task, on every path that dispatches one.** The staffing statement
  already exists and is already shared — `_enter_selected_task` was extracted precisely so that two
  callers could not drift (finding F45). This change gives it a third caller rather than a second
  copy: `trigger_agent_directly` stages the same two writes beside `prepare_review_turn`, which is
  the single point where *this turn is a review of task X* becomes true for both dispatch paths.
- **The staffing is idempotent, so the flow path is unaffected.** A flow-dispatched review reaches
  `trigger_agent_directly` already staffed; `_enter_selected_task`'s `WITH_REVIEWER_LOOP_TASK_STATUSES`
  branch already handles exactly that case by leaving the status alone, and the assignee write
  becomes a no-op writing back the value already there.
- **A review that cannot legally be staffed is refused before the turn is spawned.** Naming the
  task's own author as its reviewer is the case F70's guard exists to refuse, and attempting the
  staffing up front is what surfaces it as a stated refusal at trigger time instead of a
  `_guard_reviewer_is_not_the_author` failure inside a turn that has already cost money. The refusal
  keeps the guard's own wording, which already names the two remedies.
- **Two further refusals, both found by the round-2 review.** A review is refused when the named
  task is in neither a reviewable status nor already under review — without this, staffing would
  write a holder onto live work and travel no transition, taking an `in_progress` task away from the
  agent doing it and still dead-ending. And a review is refused when the task is already under review
  by a *different* agent, because replacing the holder there travels no transition either and leaves
  a handover the task's history cannot explain. See `design.md` D8 and D9.
- **Binding is untouched and stays a read.** Staffing is an act of dispatch, not of binding.
  `task_named_by` keeps meaning what it means, `review_task_id` is still not merged into `task_id`,
  and the existing requirement that binding moves nothing remains literally true — by the time the
  binding is read, the staffing has already happened, so binding still observes an unchanged task.

Deliberately **not** in this change:

- **F77** (an agent has no way to address the operator). It is severity C, its own decision, and
  once a hand-started reviewer can move the task through the ordinary lifecycle it is no longer the
  reviewer's only exit — which is the state in which F77 should be decided on its merits rather
  than under the pressure of being a workaround.
- **F75** (a task's own evidence rejected as a duplicate of itself) is already fixed.
- Refusing *without* staffing, and giving reviewers an ownership-free verdict channel, were both
  considered and rejected — see `design.md` D1.

## Capabilities

### New Capabilities

(none — this closes a gap between two existing capabilities rather than introducing a concept)

### Modified Capabilities

- `task-lifecycle-governance`: gains a requirement that dispatching a review staffs the task
  regardless of which path dispatched it, and that a review which cannot be staffed is refused
  before a turn is spawned. This is the general rule that the existing flow-only requirement — *a
  review a flow cannot staff is not reported as staffed* — is one instance of.
- `run-task-binding`: the existing requirement *a run started to review a task binds to that task*
  is clarified so that "binding a review SHALL NOT move the task" is not read as forbidding the
  staffing this change adds. Binding remains a read; the dispatch that precedes it is what moves
  the task. Without this the two requirements read as contradictory even though the code satisfies
  both.

## Impact

- `hub/hub/api/v1/agent_trigger.py` (`trigger_agent_directly`) — stage the staffing beside
  `prepare_review_turn`; translate the guard's refusal into the trigger's own refusal.
- `hub/hub/scheduler.py` — `_enter_selected_task` gains a third caller. Whether it moves out of
  `scheduler.py` to avoid an import cycle is settled in `design.md` D3.
- `hub/tests/test_review_dispatch_staffs_the_task.py` — new.
- `hub/tests/test_scheduler.py`, `hub/tests/test_review_checkout.py`, `hub/tests/test_agent_trigger.py`
  — existing coverage of both dispatch paths; extended, not replaced.
- No database migration: no column changes. No UI change: the board reads task status and assignee
  and will show the staffing it already knows how to show.
