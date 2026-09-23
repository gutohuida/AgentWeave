# Design — a flow stages its review in the dispatch

**Built on the operator's answer of 2026-09-23 to `F327-scope`: option (b).** The flow stops
staging `under_review` before the dispatch; the dispatch stages it; the reviewable pool excludes the
task by its pending entry. `DECISIONS.md` `F327-scope` (2026-09-12) had chosen (a) and recorded (b)
as *"unexamined by any round and, per R3, larger than R2 estimated, because the divergence restaff
collides with D9"*. This design examines it. If the operator reverts to (a) or chooses (c)/(d), this
change is withdrawn whole and F327 returns to the ledger; the other three B1 changes stand without it.

**Two different "D9"s.** The collision R3 named is **design D9 of the review-dispatch work**: the
holder check that refuses a review for a task already under review by someone else
(`agent_trigger.py:886-897`, commented *"Design D9"*, and its route twin `:497-507`). ROUNDS.md's
decision **D9** is F374's question, answered as `F374-fix` and built by
`a-review-no-reviewer-can-approve-goes-to-the-operator`. This document says "the holder check" for
the first.

**Requires** `a-task-is-attended-only-by-a-turn-that-will-reach-it` (`task_attendance`, with its
`review` flag and `refused` state) and is ordered after
`a-review-no-reviewer-can-approve-goes-to-the-operator` (both edit `_answer_failed_review`).

## D1 — The firing does not stage a review

`_do_fire_job` calls `enter_selected_task(..., is_review=selection.is_review)` for its primary
selection (`scheduler.py:3336-3341`) and `_stage_selection` for each additional one (`:3709`). For a
review selection both are skipped. Ordinary work keeps its `pending -> assigned` staging: nothing
refuses a work dispatch after staging in a way F319's rollback does not already undo, and work turns
are not what F327 is about.

The review entry is still queued with `review_task_id` (`:3417-3419`, `:3745-3747`), and
`trigger_agent_directly` already stages every review entry at dispatch (`agent_trigger.py:898`,
after the holder check), under the dispatch's rollback (`turn_scheduler.py:448`). A refused dispatch
therefore leaves the task `completed` with the assignee it had (its author), and no transition row.

## D2 — The pool excludes a task by its waiting review turn

In `decide_firing`, after the `WITH_REVIEWER` arm and before the documentless branch
(`scheduler.py:1924`, `if not wedged_review and not loop.spec_document_id`), for a task in
`REVIEWABLE_LOOP_TASK_STATUSES` that is not a `wedged_review`:

1. A review turn on the task (a pair from `task_attendance` whose `Attending.review` is true) that is
   **running or queued** → `in_flight.append((task.id, that agent))`, `continue`. This is the pool
   exclusion (b) names, and it is what keeps the ladder from staffing the same review twice (F45).
2. Only **refused** review turns → `unstaffed.append((task.id, <sentence>))`, `continue`, with no
   selection. The sentence: *"{agent}'s review of {task.id} ({title!r}) was queued and delivering it
   was refused: {refusal} Fix what it names, withdraw that input so the flow can staff the review
   again, or land it yourself."* — fitted like D4 of the attendance change. Re-staffing here would
   queue a second review turn behind the refused one, delivered only after it, and usually refused
   the same way.
3. Otherwise → today's code (documentless branch, attribution, commit check, ladder).

`task_attendance` is already read once per walk (change 1's D1), so this adds no query.

**Before the documentless branch, deliberately.** A review turn can be waiting on a documentless
loop's task too: the operator's own request, queued because the reviewer was busy
(`task-lifecycle-governance` *A review accepted while its reviewer was busy…*). Today that task sits
`completed`, the loop's firing puts it in `awaiting_landing`, and the card says *land it* while a
review of it is queued. And on a **flow**, the same operator request is re-staffed by the ladder
today, because nothing but the status kept a task out of the pool — a second review queued beside
the operator's. Found by reading; not filed. D2 answers both with "in flight".

## D3 — An under-review task whose replacement's turn is waiting

The `WITH_REVIEWER` arm (`scheduler.py:1718-1813` today; change 1 edits its tail) asks whether the named
holder attends the task. After D5, a restaff leaves the silent reviewer named until its
replacement's turn is dispatched, and the F70 recovery leaves the author named until its reviewer's
turn is. So, before the F70/F154 logic:

- the holder attends → `in_flight (task, holder)`, as change 1;
- else another agent's review turn on the task is running or queued → `in_flight (task, that
  agent)`; not a wedge, and not recovered again;
- else another agent's review turn on the task was refused → `unstaffed` with D2's sentence naming
  that agent;
- else → change 1's and the gate change's logic: F70 recovery, refused-delivery sentence, gate
  sentence, wedged sentence.

The `in_flight` pair names the agent the turn is for, not `task.assignee`, so the board attributes
the task to the reviewer who is about to take it (`task_attribution.attribute`,
`task_attribution.py:157-200`, reads `_cannot_staff`).

## D4 — A reviewer with a waiting review turn is not free

Today a flow reviewer is not free because it holds the `under_review` task (`LIVE_STATUSES`,
`task_transitions.py:338`) in a live loop. After D1 it holds nothing until the dispatch, and
`completed` is not a live status (`:224`). Without D4 the next firing could give the same agent a
second review while the first waits (the agent is not running because its turn has not started —
that is exactly when the review waits).

`_roster_availability` (`scheduler.py:1128-1198`) adds, for each review pair from `task_attendance`
whose agent is not the task's assignee, a `Holding(task_id, status, loop_id, reachable=True)`.
Refused review pairs count too, as D5 of change 1 counts refused input: the entry is still queued.
The rung-3 sentence then names the agent as booked on that task (`_rung_3_booked_clause`,
`:1319-1327`), which is true. One extra query loads status and `loop_id` for those task ids.

## D5 — The restaff, and the two holders a dispatch may replace (the holder-check collision)

**The restaff.** `_answer_failed_review` (`run_divergence.py:469-487`) stops writing
`task.assignee = choice.agent`. It still returns `previous_assignee` (the silent reviewer, read
before), which the `RunDivergence` row records (`:814-826`), and still queues the response with
`review_task_id` and `divergence_source_run_id` (`:475-486`). The dispatch stages it.

**The collision.** That dispatch finds the task `under_review` and held by the silent reviewer, not
by the agent dispatched, and the holder check refuses it (`agent_trigger.py:886-897`). R3 of the
F319 change saw this and stopped. Three ways out:

| Option | What it does | Cost |
|---|---|---|
| (i) keep the restaff's early write | the restaff path keeps F327's shape; a refused replacement leaves a reviewer that never ran named, and the operator's other reviewer is refused | F327 unfixed on one of its three doors (F327's own *"Reach"* names it) |
| (ii) **exempt a recorded restaff** | the dispatch replaces the holder where the entry being delivered is the divergence response to that holder's failed review | one read of the entry and its `RunDivergence`; a governance paragraph |
| (iii) exempt any holder that is not attending | replaces a holder whenever `task_attendance` says it is not on the task | contradicts *"A review already held by another reviewer is not silently taken"* for every hand-staffed silent review, which the operator did not decide |

**Recommended: (ii).** The holder check exists because *"a handover that travels no transition
leaves the task's recorded history unable to explain who holds it"* (governance, `spec.md:1902-1905`).
A restaff's handover is explained: the `RunDivergence` row names the failed run, the task, and
`previous_assignee`; the queued entry names the replacement and `divergence_source_run_id`; and
`record_response_run` links the replacement's run (`:561-580`). The rule, at the dispatch only:

> Replace the holder where an entry being delivered has `origin_type == "divergence"`,
> `review_task_id == task.id`, `agent == the dispatched agent`, and `divergence_source_run_id` naming
> a run whose agent is the current holder, for which an unresolved `RunDivergence` with
> `policy_applied == "review"` and `outcome == "restaffed"` exists.

A refused dispatch then rolls back to the silent reviewer as holder, and D3 surfaces the
replacement's refusal.

**The second holder: an author, F70's recovery.** D1 also removes the write that made F70's recovery
work (*"The assignment above is the whole repair"*, `enter_selected_task`, `scheduler.py:896-904`):
the firing re-selected a wedged `under_review` task and the firing's own `enter_selected_task`
replaced the author. Now the dispatch does it, and meets the holder check, because the author is a
holder that is not the dispatched agent. The requirement already says the refusal is for a task
*"held by a different reviewer"*, and an author is not a reviewer — `_guard_reviewer_is_not_the_author`
refuses a task entering review with it as holder (`task_transition_service.py:390-440`). So the
check replaces an author holder at both sites (route and dispatch), judged by the same rule that
guard applies, called rather than restated. This changes no answer the operator gets today except
the one the F70 recovery never reaches.

## D6 — The review briefing says the status the reviewer will find

`_briefing_verdict_lines` writes *"The task is `{task.status}`: set it to `approved` … or
`revision_needed`"* (`scheduler.py:2569-2571`). Composed at the firing, that is now `completed`, from
which neither verdict is a legal edge. The dispatch moves it to `under_review` before the turn starts
or the turn does not start, so the line states `under_review` for a review briefing. The turn
context channel (`api/v1/agents.py`) is built at spawn and already reads the staged status.

## D7 — Comments that become false

- `agent_trigger.py:881-885`: *"Cannot fire on the flow path: a flow writes its reviewer into
  `assignee` and commits before the turn is scheduled"*.
- `enter_selected_task`'s docstring (`scheduler.py:851-853`: three callers).
- `_do_fire_job`'s comment at `:3327-3335`.
- `run_divergence._answer_failed_review`'s *"Reassigned for the same reason escalation reassigns"*
  (`:470-474`).

## D8 — Existing tests that move, deliberately

Every assertion that a flow firing **alone** (with `schedule_agent` mocked, so no dispatch runs)
leaves a review task `under_review` with the reviewer as assignee now sees `completed` with the
author. By `grep -ln under_review` over the files that fire a flow, the candidates are
`test_review_leaves_the_pool.py`, `test_flow_fires_a_review_turn.py`,
`test_reviewer_is_not_the_author.py`, `test_flow_width.py`, `test_flow_chain_end_to_end.py`,
`test_the_evidence_names_the_author.py`, `test_a_flow_names_what_it_cannot_staff.py`,
`test_actor_aware_claimability.py`, `test_board_agent_role.py`, `test_scheduler.py`. **R2 must
enumerate the real set by running the suite against a prototype of D1 alone**, and for each failing
assertion decide: assert the waiting review entry and the in-flight pair instead (the pool is still
closed), or let the real dispatch run. None may be deleted.

## What each route returns when the function it calls raises

- `POST /agent/trigger` (review by hand): the holder check gains two reads (`completion_attribution`
  and the evidence authors, already imported there, `agent_trigger.py:486-489`). A database error is
  a 500 today at the same place.
- The dispatch inside `schedule_agent`: the restaff exemption reads the entry, a `Run` and a
  `RunDivergence`. A failure raises inside `trigger_agent_directly`, which `_attempt_turn` does not
  catch except as `TriggerAgentError` — today's behaviour for any read there. R2 should decide
  whether the exemption's read belongs before the staging (it does: the check precedes
  `enter_selected_task`) so that nothing is staged when it raises.
- `decide_firing`'s callers (firing, board `jobs.py:380`, `run_job` `jobs.py:1335`): D2–D4 add no
  query beyond D4's one status read.

## Residuals, not fixed here

- **The holder check's sentence is false for a silent holder.** A review that gave no verdict and
  was surfaced (declared, or nobody left) leaves its reviewer named. The operator's request for a
  different reviewer is refused *"Let the review in flight finish"* — no review is in flight. The
  refusal is required (the operator did not decide otherwise); its wording is not. Candidate
  finding.
- **An operator's "Land it" on a `completed` task with a flow review waiting.** The waiting entry
  is released by `release_bindings_to` when the task is decided (`run_task_binding.py:605-650`); R2
  should confirm that path runs from `land_task`.

## Round log

- **R1, 2026-09-24** (bundle B1): wrote this change from the code at `404c7d5`, on the operator's
  (b).
