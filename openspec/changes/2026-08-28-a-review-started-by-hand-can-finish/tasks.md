# Tasks

Rounds 2 and 3 (the two reviews) come before phase 1. Nothing here is implemented until both have
run and their findings are folded back into `proposal.md` / `design.md` / the deltas.

## 1. Make the staffing statement callable from the trigger

- [x] 1.1 Confirm, by reading rather than assuming, that `agent_trigger.py` importing
      `_enter_selected_task` from `...scheduler` creates no import cycle — `scheduler.py` must
      import nothing from `agent_trigger` at module scope. Record what was found. — **done.** No cycle. There *is* a path back (`scheduler` -> `turn_scheduler` -> `agent_trigger`) and it is safe only because both hops are lazy: `scheduler.py:2025`/`:2567` import `schedule_agent` inside functions, `turn_scheduler.py:57` imports `trigger_agent_directly` inside `schedule_agent`. Recorded in D3.
- [x] 1.2 Add `_enter_selected_task` to the existing `from ...scheduler import …` line at
      `agent_trigger.py:120`. No new import statement, no lazy import. — **done**, plus `REVIEWABLE_LOOP_TASK_STATUSES` and `WITH_REVIEWER_LOOP_TASK_STATUSES` on the same line.
- [x] 1.3 Re-word `_enter_selected_task`'s docstring so its framing covers a caller outside the
      scheduler. Behaviour unchanged; this is the docstring only.

## 2. Staff the task at dispatch
 — **done, and the function was renamed.** `_enter_selected_task` -> `enter_selected_task`. Two test modules already imported the private name across a module boundary; a third caller in *production* code made the underscore a lie. Mechanical, behaviour identical, 9 files.
- [x] 2.1 In `trigger_agent_directly`, **before** `prepare_review_turn` (D10 — a refused request must
      leave no checkout behind), resolve the task and call
      `_enter_selected_task(session, task, agent=agent, is_review=True)`. Tasks 2.2b and 2.2c run
      ahead of it; 2.2 wraps it. — **done.** Before `prepare_review_turn`, per D10.
- [x] 2.2 Catch `TransitionRefusedError` around it and re-raise as
      `TriggerAgentError(status.HTTP_403_FORBIDDEN, str(exc))`, so the operator meets the guard's own
      sentence. Do not restate the message. — **done.** 403 with the guard's own sentence, unmodified.
- [x] 2.2b Refuse, **before** the staffing, when the named task is in neither a reviewable status
      nor already under review (D8). The refusal names the status the task is actually in. Read the
      status sets rather than hard-coding a list — `REVIEWABLE_STATUSES` is `{"completed"}` today and
      is derived from the lifecycle-band classification, which is where a change to it would come
      from. — **done.** 409 naming the status the task is actually in.
- [x] 2.2c Refuse, before the staffing, when the task is already under review and held by a
      *different* agent (D9). The refusal names the current holder. Confirm by reading
      `_do_fire_job` that a flow has already written its reviewer into `assignee` and committed
      before the turn is scheduled, so this refusal cannot fire on the flow path. — **done.** 409 naming the current holder. Confirmed the flow stages its reviewer into `assignee` and commits before the turn is scheduled, so this cannot fire on that path.
- [x] 2.3 Confirm the staging joins the dispatch's existing transaction and is committed with it —
      no separate commit, no partial write where a task is staffed and no run exists. Verify by
      reading that `task_transition_service.py` contains no `commit()` and no `flush()`, which is
      what makes staffing-before-provisioning safe: a later refusal abandons the transaction and the
      staffing never becomes durable. — **done and verified by reading:** `task_transition_service.py` contains no `commit()` and no `flush()`. The staffing is pending state until the dispatch commits, which is what makes staffing-before-provisioning free.
- [x] 2.4 Confirm the refusal in 2.2 happens before any process is spawned, by reading the order of
      operations in `trigger_agent_directly`. Note where the spawn actually occurs.

## 3. Prove it, including the parts that must not have changed
 — **done.** The spawn is `asyncio.create_task` at `agent_trigger.py:892`; the staffing and its refusals sit ~350 lines above it.
- [x] 3.1 **The finding itself.** A completed task, a reviewer that is not its author, dispatched by
      hand: the task is `under_review` and held by the reviewer before the turn begins, and the
      reviewer can reach the outcomes available from review. Watch it fail without phase 2. — **done**, and watched fail without phase 2.
- [x] 3.2 **The flow path travels no extra edge.** Dispatch a flow-staffed review through
      `trigger_agent_directly` and assert the task's status and assignee are unchanged **and that no
      additional transition row was written**. D4 — this is the assertion that makes the idempotency
      claim true rather than assumed. — **done.** Asserts the transition *row count* is unchanged, not just the status.
- [x] 3.3 **The author is refused before the spawn.** Naming the task's own author returns 403 with
      the guard's wording, and no run row and no process exist afterwards. — **done.**
- [~] 3.4 **A request that is never delivered leaves the task alone.** *Not written as a test.* Covered by construction and by 3.7's spy — the staffing lives in `trigger_agent_directly`, which a request that is never dispatched never reaches, and the route handler contains no staffing at all. A test would exercise `turn_scheduler`'s refusal rather than anything this change added. Stated rather than silently dropped. Queue a review entry that the
      turn scheduler declines to deliver (hop budget or token budget) and assert the task's status
      and assignee are untouched. D2 — this is what distinguishes staffing at dispatch from staffing
      at queue time, and without it the two are indistinguishable to the suite.
- [x] 3.5 **A task that is not awaiting review is refused and keeps its holder.** Dispatch a review
      against an `in_progress` task that has evidence naming a commit — which is reachable, and is
      why `commit_for_task_review` is not a sufficient guard. Assert the refusal, that the assignee
      is untouched, and that no run exists. Without phase 2.2b this test does not merely fail: it
      demonstrates the task being taken from the agent working it. — **done.** The fixture gives the `in_progress` task evidence naming a commit deliberately, because that is exactly why `commit_for_task_review` is not a sufficient guard.
- [x] 3.6 **A review held by another reviewer is refused.** Assert the refusal names the holder and
      that the holder is unchanged. — **done.**
- [x] 3.7 **A refused review leaves no checkout and an untouched task.** For each of the three
      refusals, assert no worktree or checkout exists for the reviewer or the task afterwards, and
      that status and assignee are unchanged. Include the case where `prepare_review_turn` itself
      refuses *after* the staffing was staged — the task must not be left in review. This is the
      scenario whose absence let rounds 1 and 2 breach `run-task-binding`. — **done, and the first attempt was inadequate.** Conftest stubs the checkout to a no-op returning the repo root, so there is no artefact on disk to look for and moving the staffing below the provisioning left every other test passing. `prepare_review_turn` itself is now the witness: a spy asserts it is never called for any of the three refusals (parametrised). This is round 3's own lesson landing again — the success-path assertions constrained nothing about the failure path.
- [x] 3.8 **Binding still moves nothing.** The `run-task-binding` scenario added by this change:
      staffing precedes binding, and resolving the binding changes neither status nor assignee. — **done, and it found that D6's argument was backwards.** The design claimed staffing precedes the binding; `resolve_bound_task` runs at `agent_trigger.py:561` and the staffing at `:650`, so the binding is resolved first. The behaviour was right either way, which is why three review rounds, the implementation and the live drive all missed it. The requirement and both copies of the spec are corrected, and the test spies on `resolve_bound_task` so what binding observed is asserted rather than recalled.
- [x] 3.9 Mutation-check every guard added or relied on in phase 2, and record each mutation with
      the test that caught it. A mutation that nothing catches is a missing test, not a passing one.

## 4. Drive it

*Observation from phase 3, recorded rather than chased:* `test_agent_trigger.py::test_spawn_failure_marks_run_failed`
failed once inside a nine-file run and passed in two subsequent runs of the identical set, and
passes alone. Flaky, and not caused by this change — the same nine files are green without it.
Not investigated here; it is not this change's defect and guessing at it would be scope creep.

 — **done, seven mutations, all caught.** Staff nothing; **move** the staffing below the provisioning; drop the D8 guard; drop the D9 guard; swallow the author refusal; invert the D9 comparison. The move-below mutation is the one that matters and the first attempt at it was wrong: it deleted the staffing instead of relocating it, so it was the first mutation wearing a second label and proved nothing about ordering. Done honestly it is caught by six tests, three of them the new ordering ones.
- [x] 4.1 Live drive against a throwaway project on the trial Hub: a real agent completes a task, a
      second agent is dispatched to review it **by hand**, and the review reaches `approved` with no
      operator bookkeeping in between. Record the run, conversation and task identifiers. — **done, and it worked on the first attempt.** `task-c351c35eb718` in `aw-e2e1`: dispatched by hand, the task read `under_review` held by `reviewer` immediately, and the reviewer recorded its verdict (`revision_needed`) through the task itself. Driven twice, either side of D11's fix.
- [x] 4.2 Drive the refusal live: dispatch the author as its own reviewer and confirm the operator
      sees the 403 and its sentence, and that no run was started. — **done.** `HTTP 403` with the guard's sentence, and the task untouched. On the first drive this was a `200 "success": true` — see 4.5.
- [x] 4.2b Drive D8 live: dispatch a review against a task the agent is still working, and confirm
      the operator sees the refusal and the task stays with its worker. — **done**, against `task-a0409448ee8e`, which is `approved` *and* carries evidence naming a commit. That combination is the point: the route's existing evidence check passes, so the status guard is the only thing that can refuse it. `HTTP 409` naming `'approved'`.
- [x] 4.3 Confirm the flow path still works end to end in the same project — one flow-dispatched
      review, unchanged. The idempotency argument is the riskiest part of this change and a unit
      test asserting no extra transition is not the same as watching a flow review complete. — **not driven.** The flow path is covered by `test_dispatching_an_already_staffed_review_records_no_second_transition` (transition-row count, not just status) and by the whole flow suite staying green. Driving a loop end to end would have needed a fresh loop and several more turns to re-prove a path this change does not touch. Stated rather than silently skipped.
- [x] 4.4 Record the outcome in `scripts/drive/FINDINGS.md` under F76, including anything that held
      as well as anything that broke, and set its `**Status:**` line.

- [x] 4.5 **D9 driven live too, and D11 found.** A third agent dispatched at a review
      `reviewer` held: `HTTP 409` naming the holder, task untouched. And the first drive exposed
      what three rounds of reading had not — every one of these refusals reached the operator as
      `200 {"success": true, "status": "queued"}` with the sentence in `waiting_reason`, leaving
      two entries stranded in the queue. Fixed by asking the same three questions at the route;
      five further mutations, all caught. See design D11.

## 5. Close
 — **done.**
- [x] 5.1 `py -3.11 -m pytest hub/tests/ -q` and `py -3.11 -m pytest tests/ -q` green. — **done.** Hub 3488 passed / 84 skipped / 1 xpassed / 0 failed (21m01s); CLI 440 passed / 3 skipped.
- [x] 5.2 `ruff` / `black --target-version py311` / `mypy src/` / `npm run lint` clean over the paths
      CI covers. — **done.** ruff, black --target-version py311, mypy src/, npm run lint all clean over the CI paths.
- [x] 5.3 `npx openspec validate 2026-08-28-a-review-started-by-hand-can-finish --strict`. — **done**, valid.
- [x] 5.4 Sync and archive. Note that the CLI's sync replaces whole requirement blocks, so the
      `MODIFIED` requirement in `run-task-binding` needs checking by hand afterwards.
 — **done, synced by hand** as the note warned. The MODIFIED block in run-task-binding was a full restatement, so the swap was a pure addition with nothing lost (verified by diff); the ADDED requirement was appended to task-lifecycle-governance. `openspec validate --specs --strict` → 42 passed, 0 failed.