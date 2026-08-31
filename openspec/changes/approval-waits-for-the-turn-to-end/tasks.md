## 1. Reproduce F162 before fixing anything

- [x] 1.1 Write a failing test that reproduces the window in `hub/tests/`: a task whose bound run is
  live, moved to `approved`, currently yielding a recorded `ALREADY_INTEGRATED` skip against the
  **base** commit and a task reading `approved`. Assert today's wrong behaviour so the test flips.
- [x] 1.2 Assert the consequence, not only the state: the task's work is *not* an ancestor of the
  project's main branch after the approval, and the recorded integration is not retryable.
- [x] 1.3 Confirm the test fails for the stated reason by reading its failure output, not by
  assuming — a test that passes today is reproducing something else.

## 2. The liveness predicate

- [x] 2.1 Test the predicate directly: a run this Hub process owns and holds a live handle for reads
  live; a run recorded `running` with no handle in this process reads **not** live; an
  app-server run in `_active_app_server_runs` reads live.
- [x] 2.2 Implement the predicate in `hub/hub/run_liveness.py`, which owns `active_ptys` and
  `active_app_server_runs`; `agent_trigger` registers into it and `requirement_gate` imports it
  (design D3, open question 2 answered). Registry first; absence means not live. Move the five test
  files' references with it.
- [x] 2.3 Do not use `pid_alive` as the sole test, and record why in a comment citing its own
  docstring's warning about a caller that checks a process this same Hub killed
  (`pty_runner.py:150-156`).
- [x] 2.4 Scope it to runs bound to this task (`Run.task_id`), and note the unbound-run residual in
  a comment so it is a known gap rather than an oversight.
- [x] 2.5 **Exclude the acting run** (design D10). Widen `evaluate` by a keyword-only
  `acting_run_id=None` and pass `actor.run_id` from `task_transition_service`. Test it directly: a
  run bound to the task approving *itself* is permitted; a *second* live run bound to the same task
  still refuses. Comment it with why — `run_task_binding.task_named_by` binds a review run to the
  task it inspects (`:170-189`, migration `0092`), so without this every flow review is refused.
  `evaluate` has exactly one caller (`task_transition_service.py:555`), checked rather than assumed,
  so no second surface has to be kept in step with the widened signature.
- [x] 2.6 **Pin D10's residual in a test rather than leaving it in prose** (design D10, round 3). A
  *working* run bound to a task whose `completed` was recorded by the **operator** and whose assignee
  was cleared can approve from inside its own live turn: `_bind` sets `run.task_id` for a working
  turn too (`run_task_binding.py:427`), and `_guard_author_is_not_reviewer` permits where no
  completing agent is recorded (`task_transition_service.py:304-305`). Assert that shape explicitly,
  named as a known residual, so the behaviour is a decision on the record and a later change that
  makes the `InboundQueueEntry.review_task_id` join cheap knows exactly what it is closing.

## 3. The gate refuses a live turn

- [x] 3.1 Test each scenario in `specs/task-lifecycle-governance/spec.md`: refused during the turn;
  permitted after it; not refused when the process is gone; unaffected with no run; refused
  identically at `sketch` and `gate` rigor.
- [x] 3.2 Add the fifth `GateRefusal` category with the comment its four siblings each have, stating
  what kind of claim it is and why it is not one of the others — and add it in **all four** places:
  the field, `refuses` (`:112`), `detail()` (`:120`) and `to_dict()` (`:193`). A field missing from
  `refuses` is a category that never refuses; one missing from `to_dict` is a refusal no surface can
  render.
- [x] 3.3 Implement the check in `evaluate`, **above** the `if not enforced` early return, and
  **beside** the `if situation is not None` block rather than inside it (design D1, round 2):
  `_merge_situation` returns `None` for any project with no main branch or unresolvable workspace,
  and liveness is not a question about the repository. The comment SHALL state why this departs from
  `_MergeSituation`'s *"a reason to not know, never a reason to refuse"* (`requirement_gate.py:230-238`,
  round 3) — it is not one of that docstring's four preconditions, its remedy clears itself, and
  `approved` is a judgement about work even where nothing merges.
- [x] 3.9 Test the departure directly (round 3): a task in a project `_merge_situation` cannot
  resolve — no configured main branch — is still refused while its turn is live, and still approves
  normally once the turn ends. This is the interaction with
  `task-lifecycle-governance:720` and it must be pinned rather than left to be re-derived.
- [x] 3.4 Compose its sentence in `detail()` alongside the others — never as an early return
  (`requirement_gate.py:115-124` records why that mattered once already).
- [x] 3.5 Write the refusal sentence so it names the agent, states that the turn is still running,
  and says the refusal clears itself when the turn ends. It must not read as a defect in the work
  (design D4).
- [x] 3.6 Verify the sentence survives the UI's error path the way F152's fix did — check
  `readableApiError` renders it as prose, not a dict repr.
- [x] 3.7 Re-run task 1's reproduction; it must now assert the refusal.
- [x] 3.8 Add a regression test that a flow's reviewer can still approve the task it reviewed — the
  populated shape, with the review run bound to that task. This is the change's largest regression
  risk (design D10).

## 4. The evidence route shares the window — cover it

Round 2 answered this at the source (design D9): **it does.** `_targets` does not filter on
`reachable_from_main`, a footprint recorded mid-turn names the pre-turn commit by construction, and
`restamp_run_footprints` runs at turn end and re-merges nothing. What remains is proving it.

- [x] 4.1 Determine whether approving mid-turn on the evidence route merges a stale commit. Answered
  in design D9: yes, by the same mechanism, through the other door.
- [x] 4.2 Add a test covering the evidence route through the same refusal: a task whose accepted
  evidence names a commit, approved while the run that recorded it is still live, refused.
- [x] 4.3 The requirement's rationale names both routes rather than the branch-tip one alone (already
  written into the delta by round 2 — confirm it still reads true after implementation).

## 5. A loop stops entering the review arm

- [ ] 5.1 Test the `agent-loops` scenarios: a loop's completed task is not selected for review; no
  firing reports a missing commit to review; the unstaffed report stays empty for it; a flow's
  review leg is unchanged.
- [ ] 5.2 Implement the exclusion at the selection site in `scheduler.py` (design D5), not inside
  `commit_for_task_review`. **On the fresh-review branch only** (round 3): the same block is reached
  by `wedged_review` rows carried down from `scheduler.py:1299-1356`, which is the F70 recovery of a
  task already in `under_review` under its own author's name. That path deliberately records no
  `in_flight` entry (`:1349`), so a wholesale exclusion would drop such a row out of the walk in
  total silence.
- [ ] 5.3 Make sure the loop's completed task does not reach `unstaffed` — it is not a step anything
  failed at.
- [ ] 5.4 **And does not fall to the generic stall sentence either** (round 3). Without the arm,
  `_stall_reason_from_walk` emits *"no claimable task among 1 open (1 completed)"*
  (`scheduler.py:1668`) — F142's measured-live sentence, re-earned for loops on the day it is removed
  for flows. Give the firing a stall reason that names the completed work as waiting for the
  operator's landing action. Test it.
- [ ] 5.5 **Move the flow fixtures onto documents** (round 3, and this is the item task 5.4 used to
  understate). Five test files construct `Loop(...)` with no `spec_document_id` and assert the review
  arm through `decide_firing`: `test_actor_aware_claimability.py` (`:428`),
  `test_a_flow_names_what_it_cannot_staff.py`, `test_review_dispatch_staffs_the_task.py`,
  `test_review_leaves_the_pool.py`, `test_a_review_needs_something_to_review.py`. Where the test's
  subject is a **flow** requirement, the fixture declares a document — the exclusion is not weakened
  to keep a fixture passing. Where the subject is genuinely a loop, the expectation changes with this
  requirement. Say in each which of the two it was.
- [ ] 5.6 Assert the two things D5 does **not** remove (round 3): the operator can still start a
  review of a loop's completed task by hand (`task-lifecycle-governance:1481`), and a loop's
  `under_review` row wedged under its own author still recovers through the ladder without moving
  status (`:317`).

## 6. One action lands a loop's work

- [ ] 6.1 Test the `agent-loops` landing scenarios: one action reaches `approved` and merges; each
  transition is recorded and attributed to the operator; the action is refused while the turn is
  live; a refused landing leaves holder, status and integration record untouched.
- [ ] 6.2 Implement it as a composition of the existing transitions (design D6). Do not add
  `completed -> approved` to `TRANSITIONS`.
- [ ] 6.3 Evaluate the gate before performing any transition (design D7) — **and perform all three
  in one handler under one commit** (round 3). `apply_transition` does not commit; the routes in
  `api/v1/tasks.py` do (`:1173`, `:1397`, `:1564`). The transaction is what makes "refused for any
  reason leaves nothing half-applied" true; the pre-check only makes the *message* the one approval
  would have given. Test a refusal raised on step two — `_guard_reviewer_is_not_the_author` on
  `-> under_review` — and assert the author's hold is still in place afterwards.
- [ ] 6.5 Record all three transitions as **actor-caused**, not `ORIGIN_RUNTIME`
  (`task-lifecycle-governance:168`, round 3). Nothing here is a move the runtime made from something
  it observed; the operator asked for every step, in one word instead of three. Assert the recorded
  cause, not only the actor kind.
- [ ] 6.4 Add the UI affordance that issues it, and render the live-turn refusal where the operator
  takes the action.

## 7. Prove it end to end

- [ ] 7.1 Re-run `scripts/drive/t_f162_window.py` against a Hub restarted from this branch. Lane 1
  must now reach a refusal instead of `REPRODUCED`; update the harness's pass condition and say in
  `FINDINGS.md` what changed.
- [ ] 7.2 Re-run `scripts/drive/t_drive2_loop_lands.py`: a loop's work still reaches the main branch,
  now in one operator action, with no review stall on the way.
- [ ] 7.3 Re-run `scripts/drive/t_drive1_flow_lands.py`: the flow still lands its work and its review
  leg is untouched.
- [ ] 7.4 Record the outcome of each drive in `scripts/drive/FINDINGS.md`, including anything new the
  drives surface.

## 8. Close it out

- [ ] 8.1 `openspec validate approval-waits-for-the-turn-to-end --strict`.
- [ ] 8.2 `pytest hub/tests/ -v` with `py -3.11`, and the CLI suite if anything under `src/` moved.
- [ ] 8.3 `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/
  hub/tests/ tests/`, `mypy src/`.
- [ ] 8.4 If `hub/ui/src` changed, rebuild and refresh the bundle with
  `py -3.11 scripts/refresh_ui_bundle.py`, and commit source and bundle together.
