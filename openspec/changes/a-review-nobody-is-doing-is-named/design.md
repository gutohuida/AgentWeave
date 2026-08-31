## Context

`decide_firing` walks a loop's queue and puts every candidate into one of five collections —
`selections`, `gated`, `deferred`, `unstaffed`, `in_flight` — then picks a decision kind from what
it has. The `WITH_REVIEWER` branch (`scheduler.py:1313-1361`) handles a task already in
`under_review`. It is deliberately not staffable by anybody: the reviewer finishes it, or the
operator takes one of `under_review`'s three exits. Its own comment says the row is kept so the
wedge is *"a stall the operator can see and act on"*. The row is kept. What is said about it is
false, because the branch appends to `in_flight` on `task.assignee` alone (`:1355-1361`) and
`DECISION_IN_FLIGHT` means, in its own words, *"every candidate is already being worked by an agent
mid-turn"* (`:942-946`).

Three lines above the walk, `held = await tasks_held_by_a_running_turn(...)` (`:1291`) already
answers *is a turn running on this task*. The ordinary-work arm consults it (`:1383-1386`). The
review arm does not.

**The same fact is repaired downstream for display.** `task_attribution.attribute` reads the
firing's cannot-staff collection and asks the runs table before choosing a word: `unstaffable` plus
a live run is `working`, `unstaffable` with nothing running is `held`
(`task_attribution.py:186-188`), and `held` exists because of F63 — *"the scheduler records an
`under_review` task as in-flight whether or not anybody is running it"* (`schemas/jobs.py:142-143`).
So the board is right and the firing is wrong about one fact, and the module holding the correction
says so: *"**Not** 'is running' — that is the confusion this whole module exists to end"*
(`task_attribution.py:132-134`).

Measured, not assumed — `scripts/drive/t_f154_wedged_review.py` against `master` at `d546a8f`, Hub
restarted from that commit, **16/16**: two firings answer `409 "…nothing is wrong…"` minutes apart,
no run starts either time, `stall_reason` is `null`, and one hand transition to `revision_needed`
frees it immediately.

## Goals / Non-Goals

**Goals.** A firing acts on the same version of "is anybody working this" the board displays. A
queue whose only non-terminal work is a review nobody is doing refuses with a sentence naming the
task and the agent. Both populations — a review turn that ended without a verdict, and a task an
operator walked into `under_review` by hand — reach that outcome by one rule.

**Non-Goals.** No second re-staffing path (`run_divergence._answer_failed_review` owns that). No
change to `under_review`'s exits. No repair of `agents_that_worked`'s blindness to operator-walked
edges (F167). No widening of `held` itself, whose caller in the ordinary-work arm is asking a
different question — *may a turn start on this checkout* (design D8) — and must keep asking it.

## Decisions

### D1 — The fix is in the decision, not in the collection

The task **stays** in `in_flight`/`_cannot_staff`. `DECISION_IN_FLIGHT` is chosen only where at
least one member of that collection has a turn behind it.

*Rejected:* moving the row to `unstaffed`. It reads as the tidier repair and it silently reverts
F63: `staffing_from_decision` builds `unstaffable` from `_cannot_staff`, so a row removed from it
falls through `attribute`'s branches to `task.assignee` and the board's capacity changes from `held`
to `assigned`. The tripwire is that nothing in the scheduler's own tests would notice — the
regression is two modules away, in a field the firing never reads.

*Rejected:* a new sixth collection. `_cannot_staff` already means *"the firing cannot staff anybody
onto this"*, which stays exactly true for a wedged review. The defect is not the classification, it
is the inference drawn from it.

### D2 — "Somebody is on it" is a running turn **or** an undelivered queue entry

The predicate is not `held` alone. `schedule_agent` (`turn_scheduler.py:78-105`) can leave a
correctly staffed review durably **queued** rather than running — `waiting_reason="agent is already
running"`, an exhausted hop budget, an exhausted token budget, an unavailable conversation — and
`run_divergence._queue_response` (`:815`) queues the replacement reviewer's turn the same way. A
predicate that asked only about running turns would call those reviews abandoned while they are
waiting their turn, and would do it on the tick immediately after a correct staffing.

So: a turn bound to the task is `running`, **or** an `InboundQueueEntry` with `state == "queued"`
names the task in `task_id` or `review_task_id`. `state` is the right column: `"withdrawn"` already
means *"this will never be delivered"* (`db/models.py:574-577`), so an abandoned entry correctly
stops counting as attendance.

*Rejected:* `run_liveness.live_turn_for_task`, today's new registry. It answers about *this process*,
which is right for the approval gate it was built for and wrong here: it would call every run of a
previous Hub process absent, and a Hub bounced mid-review would report a stall for a review that
`reconcile_interrupted_runs` is about to reconcile properly at startup. The runs table is the
board's own source and is the one to match.

### D3 — Where the predicate lives

Beside `tasks_held_by_a_running_turn` in `run_task_binding.py:267-295`, as a second function
returning the same `task_id -> agent` map shape, with the queue-entry arm added. Both are read once
per walk and passed in, matching how `held`, `free` and `running` are already asked once before the
loop for the reason stated at `scheduler.py:1283-1291`.

*Rejected:* widening `tasks_held_by_a_running_turn` to include queued entries. Its docstring records
that its two callers ask two different questions of one query; the trigger path's question is *may
this turn start*, and a queued entry must not stop a turn starting. One more caller with a third
meaning is what that docstring warns against.

### D4 — The sentence, and where it is promoted

The wedged row is appended to **`unstaffed` as well as** `in_flight`. Dual membership is the
mechanism, not an accident of it: `_cannot_staff` is what keeps the board saying `held` (D1), and
`unstaffed` is what carries the sentence — the F64 rule at `scheduler.py:1590-1609` promotes
`unstaffed[0][1]` to `stall_reason`, and `scheduler.py:2585` emits one `review_unstaffed` per entry.
Round 1 said "a walk-local list" and "promoted by the existing F64 rule" in the same breath; those
are only both true if the list *is* `unstaffed`.

**The fall-through cannot reach `PROCEED_EMPTY`, and that was worth checking rather than assuming.**
`decide_firing` returns `DECISION_PROCEED_EMPTY` when `_stall_reason_from_walk` answers `None`
(`:1585-1589`), which would fire an agent to fill the queue — on this population, every tick,
forever. It answers `None` only when the loop has no task outside `TERMINAL_FOR_BINDING`
(`:1706-1716`), and that tuple is `TERMINAL_STATUSES` = `{"approved", "rejected"}`
(`task_transition_service.py:628`, `run_task_binding.py:465`). `under_review` is not in it, so the
walk always produces a sentence for this row and the F64 rule then replaces it with ours.

The sentence must not say the work is being done, and must not promise that a later firing picks it
up. That promise is the specific falsehood F154 records, because for this row it can never come
true.

### D6 — What the operator's Run button actually returns, checked at the route

The 409 the operator sees is **not** rendered from `FiringDecision`. `POST /jobs/{id}/run` reads the
latest `JobRun`: if its status is `"skipped"` it answers `409` with that row's `error_summary`
(`api/v1/jobs.py:1263-1267`); only if there is no such row does it consult
`_loop_work_is_all_in_flight` (`:1186-1204`), which re-runs `decide_firing` and checks for
`DECISION_IN_FLIGHT`, and failing that returns **500 "Failed to fire job"** (`:1277-1285`).

So the repair's user-visible outcome depends on the stalled path writing that row, which it does:
first stall sets `run.status = "skipped"` and `run.error_summary = stall_reason`
(`scheduler.py:2648-2649`), and a *continuing* stall increments `tick_count` on the existing row and
discards the new one (`:2628-2646`), leaving the same skipped row as the latest. Both presses
therefore answer `409` with our sentence, and the 500 branch is not reachable for this population.

This is the check the round discipline exists for: `_loop_work_is_all_in_flight` answering `False`
after the fix is *correct*, and would have been a regression from a calm wrong answer to an alarming
one if the skipped row were not written first. It is asserted at the route, not reasoned about.

### D5 — Ordering, and what must not move

The `in_flight` branch stays above the stall check (F23). The change is only that the branch is
entered on a stronger condition. A flow whose candidates are genuinely mid-turn must still report in
flight, and `t_f154_wedged_review.py` LANE 5's author-wedged row must reach the same new sentence as
LANE 1's reviewer-wedged row, because the predicate does not ask who the assignee is.

## Risks / Trade-offs

- **A tick landing inside the staffing window.** Mitigated by D2's queue-entry arm: between
  `enter_selected_task` writing the assignee and the run reaching `running`, an entry naming the
  task is already `queued`. The window where neither holds is inside one request and closed by the
  same transaction; a test asserts the staffed-but-queued case reports no stall.
- **A crashed Hub leaves `Run.status == "running"`.** Then the wedge stays hidden until
  `reconcile_interrupted_runs` runs at startup (`run_reconciliation.py:50-67`), which is the same
  bound every other consumer of the runs table already lives with — including the board, which
  would report `working` for the same row. Accepting the board's own bound is the point of D2;
  inventing a different one here is how the two surfaces start disagreeing again.
- **A queued entry that never drains.** An entry stuck `queued` behind an exhausted budget counts as
  attendance and would hide the wedge. This is correct today — the review *is* waiting, not
  abandoned — and the budget's own surfacing owns that case. Recorded so a future finding is not
  filed against this change for it.

## Migration Plan

None. No schema change, no column, no API shape change. One decision condition, one predicate, one
sentence.

## Open Questions

1. Should the same predicate replace `task_attribution`'s downstream repair, so the fact is computed
   once rather than twice? Out of scope here — the board's repair is correct and load-bearing, and
   collapsing them is a refactor with its own risk. Worth asking once this change has driven.
