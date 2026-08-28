# Design

## Context

`trigger_agent_directly` (`hub/hub/api/v1/agent_trigger.py`) is the single point both dispatch
paths converge on. `turn_scheduler.py:125` is its only caller, and it serves the operator's
`POST /agent/trigger` and a flow's firing alike, passing `queue_entry_ids` so the function resolves
`review_task_id` off the entries when the caller did not name one. Inside it, the review branch
already refuses a work-directory conflict and provisions the checkout through
`review_turn.prepare_review_turn`.

The staffing statement also already exists, already shared: `_enter_selected_task`
(`hub/hub/scheduler.py`) writes `task.assignee = agent` and then applies `completed -> under_review`.
It was extracted, rather than written twice, because `_do_fire_job` and `_stage_selection` sit ~330
lines apart and adding the review half to one and not the other is the drift finding F45 recorded.
This change adds the third caller that finding predicted.

## Goals / Non-Goals

**Goals**

- A review dispatched by hand leaves the reviewer able to record a verdict through the ordinary
  task lifecycle, exactly as a flow-dispatched one does.
- A review that cannot legally be staffed is refused before a turn is spawned, with the refusal the
  operator would have got later anyway.
- One statement of what dispatching a review does to a task, not two.

**Non-Goals**

- Changing what `review_task_id` means, or merging it into `task_id`. It still selects the commit
  to check out.
- Changing binding. Binding stays a read (`run-task-binding`: *resolving the binding SHALL remain
  a read*).
- F77, an agent's channel to the operator. Out of scope, and deliberately so — see D6.
- Any change to the flow path's observable behaviour.

## Decisions

### D1. Staff the task, and refuse up front when staffing would be illegal

**Decided by the operator, 2026-08-28.** The manual trigger performs the same staffing the
scheduler does, and refuses before spawning when the named reviewer is the task's own author.

*Rejected: refuse up front and staff nothing.* This is the cheapest repair and it is a better error
message for a hole that stays a hole — starting a review by hand would remain impossible, and the
operator's remedy would be to clear the assignee (which F78 made work) and retry, which is the
product asking a person to perform its own bookkeeping. It also leaves the two dispatch paths
divergent, which is the actual finding.

*Rejected: give reviewers a verdict channel that does not require owning the task.* The largest
option, and it answers a different question. A reviewer that can *speak* but still cannot move the
task leaves `completed -> under_review -> approved` unreachable from the manual path, so the task
still needs a human to finish it by hand. It also subsumes F77 as a side effect, which is the wrong
order: F77 deserves deciding on its merits, not as the byproduct of a repair.

### D2. Stage the staffing at dispatch, beside `prepare_review_turn` — not when the entry is queued

The route handler (`trigger_agent`) validates `review_task_id` and queues an entry; the turn may
start from a *later* call, or never. Staffing there would leave a task in `under_review` with an
assignee and no turn behind it whenever the entry is dropped, the budget is exhausted, or the hop
budget refuses delivery — which is precisely the wedge `_guard_reviewer_is_not_the_author` exists to
prevent, reintroduced one layer up. The comment on `new_entry` already states the general form of
this: anything held only at queue time is gone by the time the turn exists.

Beside `prepare_review_turn` is the moment *this turn is a review of task X* becomes true, for both
paths, and it is inside the same transaction as the rest of the dispatch.

*Rejected: staff in the route handler.* Above.
*Rejected: staff after the spawn.* F70. The guard refuses `-> under_review` while the assignee is
still the author, so the write must precede the transition; and a spawn that has already started
cannot be un-started if the staffing then refuses.

### D3. Reuse `_enter_selected_task`; the import direction already exists

`agent_trigger.py:120` already imports from `...scheduler` at module scope
(`finalize_job_run_for_conversation`), and `scheduler.py` imports nothing from `agent_trigger` at
module scope. So the third caller costs one name on an existing import line and creates no cycle.

**Round 2 established *why* that holds, which is load-bearing and was not obvious.** There is a
path back — `scheduler` -> `turn_scheduler` -> `agent_trigger` — and it is safe only because both
of its hops are lazy: `scheduler.py:2025` and `:2567` import `schedule_agent` inside functions, and
`turn_scheduler.py:57` imports `trigger_agent_directly` inside `schedule_agent`. Hoisting either to
module scope would close the loop and this import would be the edge that breaks. Stated here so a
later tidy of those lazy imports meets the reason they are lazy.

*Rejected: move `_enter_selected_task` to a neutral module.* It would be a defensible tidy, but it
is motion with no defect behind it, and it would touch two callers that are not otherwise part of
this change. If a cycle ever appears, that is when the move is justified.
*Rejected: a second copy in the trigger.* This is the exact drift F45 recorded, and the extraction
that fixed it is what makes this change small.

### D4. The staffing is idempotent, which is what leaves the flow path untouched

A flow-dispatched review arrives at `trigger_agent_directly` already staffed by `_do_fire_job`.
`_enter_selected_task` handles that case today: its `WITH_REVIEWER_LOOP_TASK_STATUSES` branch leaves
the status alone when a reviewer already holds the task, and the assignee write becomes a no-op
writing back the value already there. So the flow path travels no additional edge and records no
additional transition.

This must be **asserted, not assumed** — a second `completed -> under_review` on the flow path would
be an illegal edge, and an extra transition row on every flow-dispatched review would corrupt the
append-only history that `task-lifecycle-governance` requires. It is task 3.2.

### D5. The refusal is the guard's own, surfaced at the trigger

`_enter_selected_task` reaches `apply_transition`, which calls
`_guard_reviewer_is_not_the_author`, which raises `ActorNotPermittedError` with a message that
already names both remedies and the cost of doing nothing. The trigger catches
`TransitionRefusedError` and re-raises it as `TriggerAgentError(HTTP_403_FORBIDDEN, str(exc))`.

403, not 409: the trigger's neighbouring refusals use 409 for *this cannot be reviewed* (no commit
to review, a decided task) and the transition service's own HTTP surface answers
`ActorNotPermittedError` with 403. The operator meets the same status and the same sentence whether
they hit this by triggering a review or by attempting the transition directly, which is the point of
reusing the guard rather than restating it.

*Rejected: a bespoke pre-check that reads the completing agent and refuses before calling the
staffing.* It would duplicate `_agent_that_completed` and would drift from the guard the moment the
guard's permissive cases change (it has two, both deliberate: no assignee, and no recorded
completer). Attempting the staffing *is* the check.

### D6. Binding is not touched, and the corpus must say why that is consistent

`run-task-binding` requires *Binding a review SHALL NOT move the task*, with a scenario asserting
that the task's status and assignee are unchanged when a run binds to a task under review. Read
carelessly, this change appears to violate it.

It does not, and the reason is an ordering: staffing happens at dispatch, strictly before the
binding is resolved and read. By the time binding observes the task, it is already `under_review`
with its reviewer, and binding still changes nothing. The requirement is about what *binding* does,
not about what the task's status was on arrival.

But a requirement that is only true once you know the call order is a requirement that will be
misread, and the next person to touch this will either weaken the binding rule or refuse the
staffing. So the delta states the distinction explicitly rather than leaving it to be re-derived.

### D7. A spawn that fails after staffing leaves the task staffed, and that is correct

If the process spawn fails after the staffing is committed, the task sits `under_review` with a
reviewer that never ran. This is not new and not a regression: the flow path has had exactly this
property since F45, because `_do_fire_job` staffs before dispatching too. The task is recoverable —
it is in review, held by an agent that is not its author, so the ordinary reviewer ladder and the
operator's own transitions both still apply, and `task-lifecycle-governance`'s restaffing rule
covers the author-held case specifically.

The alternative — unwinding the staffing on a failed spawn — would mean the two paths differ again,
in the opposite direction, and would make the staffing conditional on an outcome it cannot observe
from inside the same transaction.

### D8. A task that is not reviewable is refused, before anything is staffed

**Found in round 2, and it would have shipped a defect worse than the one being fixed.**

`_enter_selected_task` writes `task.assignee = agent` *before* its status branch, and that branch
has no `else`. `REVIEWABLE_STATUSES` is exactly `{"completed"}` and `WITH_REVIEWER_STATUSES` exactly
`{"under_review"}` — so dispatching a review against a task in any other status reassigns it and
travels no transition at all.

The flow path cannot reach that state: its reviewer ladder only ever selects tasks that are already
reviewable. The manual path can, because the operator names the task id directly and the only
status-adjacent guard on that route — `commit_for_task_review` — asks whether evidence naming a
commit exists, not what the task's status is. Evidence naming a commit exists on tasks that are
still `in_progress`, so *"review this task"* aimed at live work would have taken it away from the
agent doing it, recorded nothing, and still dead-ended, since `in_progress` reaches no review
outcome either. That is strictly worse than today's behaviour, where at least nothing moves.

So the trigger SHALL refuse, before staffing, when the named task is in neither a reviewable status
nor already under review. The refusal names the task's actual status.

*Rejected: teaching `_enter_selected_task` to refuse instead.* It is shared with the flow path,
where the condition is unreachable, so the guard would live where it cannot fire and be tested
against a state its caller cannot produce — the failure mode this repository keeps finding. The
refusal belongs on the path that can actually be asked.

### D9. A review already held by a different reviewer is refused, not silently taken

**Also round 2.** The `under_review` branch is the idempotent one, but its idempotency is only
partial: the unconditional assignee write above it means dispatching a review for a task already
under review by *someone else* replaces the holder and travels no transition — a handover with
nothing in the append-only history to explain it, in a capability that requires every accepted
transition be recorded.

So a manual dispatch naming a task already under review by a different agent is refused, naming the
current holder and the remedy (reassign the task, or let the review in flight finish).

This does not touch the flow path, including the F70 recovery it depends on. A flow stages the
reviewer into `assignee` in `_do_fire_job` and commits before the turn is scheduled, so by the time
the dispatch reaches this check the holder already *is* the dispatched reviewer and the check passes
on the equality branch.

*Rejected: allow the handover.* It is a defensible operator action, and it is reachable in two
explicit recorded steps (reassign, then dispatch). Making it reachable in one unrecorded step trades
a legible history for a keystroke.

## Risks / Trade-offs

- **The meaning of `POST /agent/trigger {"review_task_id"}` changes**: it now takes ownership of the
  task, where before it only chose a checkout. That is the intended change and the reason this is a
  spec change rather than a repair, but any caller relying on "trigger a review that touches
  nothing" loses that. There is no such caller in-tree; the UI's review action is the surface that
  wants the new behaviour.
- **A refusal now happens at trigger time that previously happened mid-turn (or never).** An
  operator who today gets a run that burns tokens and ends in prose will instead get a 403. That is
  the improvement, but it is a visible behaviour change for anyone who had learned to work around
  the old one.
- **`_enter_selected_task` gains a caller outside the scheduler**, so its docstring's framing
  ("selection", "firing") becomes partly inaccurate. Task 1.3 re-words it; the function's behaviour
  is unchanged.

## Migration Plan

None. No schema change, no data backfill, no UI change. The behaviour change is confined to a
dispatch path whose current outcome is a dead end.

## Open Questions

- Should the UI's review action surface the 403 distinctly from the existing "nothing to review"
  409? Both are conflicts the operator can act on, and both already render as the API's message.
  **Round 2: not blocking, and no.** All three refusals this change can raise are sentences the
  operator can act on, and the surface already renders the API's message; a per-status branch would
  be presentation logic keyed on a number rather than on meaning.

## Review passes

**Round 2 — compare every claim to the code.** Four results. Two decisions were added that the
proposal did not have (D8, D9), one of which would otherwise have shipped a defect worse than the
finding being fixed. D3's no-cycle claim was confirmed but for an unstated reason, now stated. One
claim was confirmed as written: the spawn is `asyncio.create_task` at `agent_trigger.py:892` and
`prepare_review_turn` sits ~350 lines above it, with no process started in between, so a refusal
raised beside the staffing genuinely precedes the spawn.
