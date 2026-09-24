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
   again, or land it yourself."* — fitted like D4 of the attendance change; where the refused head
   is another entry of that agent's (`Attending.refused_here` false, the attendance change's R3 head
   rule), *"was queued behind input for {agent} whose delivery was refused: {refusal}"*. Re-staffing here would
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
whose agent is not the task's assignee **and whose task is in `REVIEWABLE_LOOP_TASK_STATUSES` or
`WITH_REVIEWER_LOOP_TASK_STATUSES`**, a `Holding(task_id, status, loop_id, reachable=True)`. The
status filter is R2's: a decided task's review entry stays queued (see Residuals), and without the
filter it would book its reviewer on an `approved` task until the entry is given up.
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
*"held by a different reviewer"*, and an author is not a reviewer. So the check replaces an author
holder at both sites (route and dispatch).

**Judged by the rule that sent the task to the ladder, not the entry guard's (R3).** R1/R2 said "the
same rule `_guard_reviewer_is_not_the_author` applies". That rule is narrower than the one that
routes a wedge to recovery: the guard reads the recorded completer, or, where no agent completed the
task, the evidence authors **alone** (`task_transition_service.py:416-433`); `decide_firing`'s wedge
predicate reads the completer, or, where none, `agents_that_worked` **∪** the evidence authors
(`scheduler.py:1777-1785`, F142 and Round 5's F167). The difference is F142's own measured case: the
agent moved the task through `in_progress`, the operator recorded `completed`, and it recorded no
evidence. The firing routes that row to the ladder, the ladder staffs a reviewer, and with the
guard's rule the dispatch would find the holder "not an author" and refuse *"already under review by
{author}. Let the review in flight finish"* — every time, since the refusal is request-level and
counted; F142's recovery, which works today only because the firing's own write needs no check, would
be lost. So the wedge predicate is lifted out of `decide_firing` into one function in
`task_transition_service` (`assignee_produced_the_work(session, task)`: completer == assignee, else
assignee ∈ `agents_that_worked` ∪ `agents_that_recorded_evidence_for`), called by `decide_firing` and
by both holder-check sites. One statement of "this holder is the author", so the recovery and the
dispatch it depends on cannot disagree. The entry guard is untouched: it answers a different
question (may *this* agent be entered as holder), where refusing on `agents_that_worked` would refuse
a staffed reviewer that was once assigned the work. This changes no answer the operator gets today
except the ones the F70/F142/F167 recovery never reaches.

**Where the exemption's read sits, and what a raise returns** (R2, task 0.2(c)). Inside the holder
check, which already precedes `enter_selected_task` (`agent_trigger.py:886-898`), so nothing is
staged when it runs. The entries it reads are the ones being delivered, which the dispatch already
reads (`_review_task_from_entries`, `:431-461`). A database error there propagates out of
`trigger_agent_directly` as any read there does today: it is not a `TriggerAgentError`, so
`_attempt_turn` does not catch it, the session is not committed, and nothing staged survives. No new
raise path.

## D6 — The review briefing says the status the reviewer will find

`_briefing_verdict_lines` writes *"The task is `{task.status}`: set it to `approved` … or
`revision_needed`"* (`scheduler.py:2569-2571`). Composed at the firing, that is now `completed`, from
which neither verdict is a legal edge. The dispatch moves it to `under_review` before the turn starts
or the turn does not start, so the line states `under_review` for a review briefing. (The
briefing's queue-count line, `select(Task.status, func.count())` at `scheduler.py:2766`, will count
the task as `completed`; that line describes the queue as it is, and stays.) The turn
context channel (`api/v1/agents.py`) is built at spawn and already reads the staged status.

## D7 — Comments that become false

- `agent_trigger.py:881-885`: *"Cannot fire on the flow path: a flow writes its reviewer into
  `assignee` and commits before the turn is scheduled"*.
- `enter_selected_task`'s docstring (`scheduler.py:851-853`: three callers).
- `_do_fire_job`'s comment at `:3327-3335`.
- `run_divergence._answer_failed_review`'s *"Reassigned for the same reason escalation reassigns"*
  (`:470-474`).

## D8 — Existing tests that move, deliberately

**R2's list, by reading** (the brief allowed reading instead of a full-suite prototype). Six sites
assert what a firing or a restaff leaves before its dispatch. Whether each moves depends on whether
the real dispatch runs inside that test (it does where `schedule_agent` reaches
`trigger_agent_directly` and the delivery commits the staging before a spawn fails), so each is named
with the rule that moves it; IMPL task 1.15 settles each by running it:

| Site | Asserts | Moved by |
|---|---|---|
| `test_reviewer_is_not_the_author.py:238-241` | a firing leaves `('under_review', REVIEWER)` | D1 — holds only if the dispatch runs in the test |
| `test_reviewer_is_not_the_author.py:286-292` | F70's wedged row restaffed to `REVIEWER`, no edge | D1 and D5's author-holder replacement |
| `test_review_divergence.py:346-348` | after `evaluate_run_end`, `assignee == "auditor"` | D5 (the restaff stops writing it) |
| `test_a_loop_staffs_the_agent_it_names.py:399-403` | after `evaluate_run_end`, `assignee == "auditor"` | D5 |
| `test_flow_chain_end_to_end.py:342-352` | the flow's `("task-chain-a", "under_review")` row is operator-attributed | D1 moves where the row is written; B3's `a-flows-own-moves-are-recorded-as-the-flows` rewrites the same pin (see Collisions) |

Not moved, checked: `test_review_leaves_the_pool.py:157-231`, `test_a_flow_names_what_it_cannot_staff.py:652-665`
and `:833-843` call `enter_selected_task` directly, which the dispatch still calls;
`test_run_divergence.py:259` is the `escalate` policy, untouched here;
`test_the_evidence_names_the_author.py:667` and `test_review_divergence.py:710` assert a surfaced,
not restaffed, review.

R1's text, kept:

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

## What the operator sees when the dispatch is refused (R3, traced from a real firing)

The firing queues the entry with `review_task_id` (`scheduler.py:3404-3429`), commits, and calls
`schedule_agent` (`:3471`). `_attempt_turn` passes the selected ids to `trigger_agent_directly`
(`turn_scheduler.py:408-423`), which reads the review task from them (`agent_trigger.py:823-824`),
finds it `completed` (no holder check), and stages it (`:898`) before `prepare_review_turn`. So
D1's staging does fire from a real flow firing, and a refusal is rolled back whole (`:448`).

- **Refused at the firing** (reviewer idle): the refusal is request-level and not transient, so
  `ScheduleResult.terminal_failure` is true (`turn_scheduler.py:683-687`) and the firing marks its
  `JobRun` `failed` with the refusal as `error_summary` (`scheduler.py:3472-3478`) — the JobCard shows
  the refusal's words. The task reads `completed`, held by its author, no transition. The next firing
  meets D2 step 2: stalled, with the refusal sentence as `stall_reason` and one `review_unstaffed`.
- **Refused later** (reviewer was running; the run-end re-drain dispatches it): no `Run` is created,
  so the refusal does not finalize the firing's `JobRun`: its `finalize_job_run_for_conversation`
  calls are all on run paths in `agent_trigger` (`:2050`, `:2193`, `:2522`, `:3065`, `:3159`), and
  otherwise only startup reconciliation settles an `in_progress` row (`run_reconciliation.py:261`) —
  confirm at IMPL which applies. The operator learns of it from the next firing's stall reason (D2 step
  2) and the queue status route's stored refusal. Pre-existing for every deferred refusal (today the
  same `JobRun` also stays `in_progress`); recorded, not fixed here. Test 1.5b pins it.

## Residuals, not fixed here

- **The holder check's sentence is false for a silent holder.** A review that gave no verdict and
  was surfaced (declared, or nobody left) leaves its reviewer named. The operator's request for a
  different reviewer is refused *"Let the review in flight finish"* — no review is in flight. The
  refusal is required (the operator did not decide otherwise); its wording is not. Candidate
  finding.
- **A decided task's waiting review entry is not released** (R2, answering R1's question; R1's
  premise was wrong). `land_task` does call `release_bindings_to` (`api/v1/tasks.py:1608`; the PATCH
  route at `:1407`), but `_release_queued_entries_bound_to` clears `task_id` only and keeps
  `review_task_id` on purpose (`run_task_binding.py:620-640`), leaving the entry `queued`. So a review
  entry waiting when its task is landed or approved is later delivered, and its dispatch refuses
  *"Task … is 'approved', which is not a status a review starts from"* (`agent_trigger.py:874`): a
  request-level, non-transient refusal, counted to `DELIVERY_ATTEMPT_LIMIT` (3,
  `inbound_queue.py:222`) and then withdrawn with a `queue_entry_abandoned` warning. Pre-existing for
  the PATCH route and for an operator's own queued request; D1 widens it to a flow's queued review.
  Bounded, costs no turn, and D4's status filter keeps it from booking the reviewer. Candidate finding
  (R2): the release should withdraw a queued entry whose `review_task_id` names the task just decided.

## Collisions with other changes (R2)

- **B3 `a-flows-own-moves-are-recorded-as-the-flows`** adds `inbound_queue_entries.job_id` and reads
  the cause of the `-> under_review` move from the delivered entries at the dispatch's
  `enter_selected_task` call (`agent_trigger.py:898`), through `_review_task_from_entries`
  (`:431-461`). After D1 that call is the flow's only review staging. So this change keeps
  `_review_task_from_entries` and the cause it returns; places D5's holder exemption above that call
  without changing its arguments; and its governance delta says staging at the dispatch does not
  change whose move it is (one sentence, compatible with B3's ADDED cause requirement in either
  order). B3's tests 1.1 and 1.3a then exercise this change's path; B3 rewrites
  `test_flow_chain_end_to_end.py:342-352`, and this change only moves where that row is written.
  **Build order: B3's change first**, and this change rebases onto its
  `enter_selected_task(..., origin, job_id)` signature.
- **`pressing-run-names-the-reason-that-held`** (unarchived): its busy guard reads
  `_agents_a_loop_may_staff` → `_roster_availability`, which D4 edits. Net availability is preserved
  (a reviewer with a waiting review turn held the `under_review` task before, and holds D4's holding
  after), so its answers do not move. No textual overlap.
- **Within B1:** built after `a-task-is-attended-only-by-a-turn-that-will-reach-it` (whose `review`
  flag is now an OR over a pair's entries, R2) and after
  `a-review-no-reviewer-can-approve-goes-to-the-operator` (both edit `_answer_failed_review`).

## Round log

- **R1, 2026-09-24** (bundle B1): wrote this change from the code at `404c7d5`, on the operator's
  (b).
- **R2, 2026-09-24** (bundle B1): re-derived against the code. Corrections: `land_task` does not
  release a waiting review entry (R1's residual premise was wrong), so D4 now filters review-pair
  holdings by status; D5's exemption read placement and raise behaviour decided; D8's movers listed
  by reading (five sites, each conditional on whether the real dispatch runs in the test); B3's
  `job_id` collision settled, B3 first; D6 notes the queue-count line. Held on re-reading:
  `enter_selected_task`'s three callers (`scheduler.py:3336`, `:3709`, `agent_trigger.py:898`); the
  holder check at `:886-897` and `review_dispatch_refusal` at `:497-507`; a `completed` task never
  meets the holder check, so D1 collides only on F70's wedge and the restaff; the restaff's assignee
  write at `run_divergence.py:469-474`; `_briefing_verdict_lines` at `:2569`.
- **R3, 2026-09-24** (bundle B1): re-derived against the code, including Round 5's F167 predicate
  (`6117d15`). Correction: D5's author-holder replacement must use the **wedge predicate's** rule
  (completer, else `agents_that_worked` ∪ evidence authors), lifted into one function shared with
  `decide_firing`; the entry guard's narrower rule would refuse F142's measured row at every dispatch
  and lose its recovery. Traced D1 from a real firing to the dispatch and recorded what the operator
  sees for an immediate and a deferred refusal (new section; test 1.5b). D2's sentence gains the
  behind-a-refused-head variant from the attendance change's R3 head rule. Held: the restaff entry
  carries both `task_id` and `review_task_id` (`run_divergence.py:475-486`), which
  `_review_task_from_entries` reads as a review, not a mixed batch (`agent_trigger.py:447-452`); the
  `RunDivergence` row is committed with the entry (`:814-827`) before the dispatch can read it.
