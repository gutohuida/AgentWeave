# Tasks

Rounds 2 and 3 (the two reviews) come before phase 1. Nothing here is implemented until both have
run and their findings are folded back into `proposal.md` / `design.md` / the deltas.

## 1. Make the staffing statement callable from the trigger

- [ ] 1.1 Confirm, by reading rather than assuming, that `agent_trigger.py` importing
      `_enter_selected_task` from `...scheduler` creates no import cycle — `scheduler.py` must
      import nothing from `agent_trigger` at module scope. Record what was found.
- [ ] 1.2 Add `_enter_selected_task` to the existing `from ...scheduler import …` line at
      `agent_trigger.py:120`. No new import statement, no lazy import.
- [ ] 1.3 Re-word `_enter_selected_task`'s docstring so its framing covers a caller outside the
      scheduler. Behaviour unchanged; this is the docstring only.

## 2. Staff the task at dispatch

- [ ] 2.1 In `trigger_agent_directly`, immediately after `prepare_review_turn` succeeds, resolve the
      task and call `_enter_selected_task(session, task, agent=agent, is_review=True)`.
- [ ] 2.2 Catch `TransitionRefusedError` around it and re-raise as
      `TriggerAgentError(status.HTTP_403_FORBIDDEN, str(exc))`, so the operator meets the guard's own
      sentence. Do not restate the message.
- [ ] 2.2b Refuse, **before** the staffing, when the named task is in neither a reviewable status
      nor already under review (D8). The refusal names the status the task is actually in. Read the
      status sets rather than hard-coding a list — `REVIEWABLE_STATUSES` is `{"completed"}` today and
      is derived from the lifecycle-band classification, which is where a change to it would come
      from.
- [ ] 2.2c Refuse, before the staffing, when the task is already under review and held by a
      *different* agent (D9). The refusal names the current holder. Confirm by reading
      `_do_fire_job` that a flow has already written its reviewer into `assignee` and committed
      before the turn is scheduled, so this refusal cannot fire on the flow path.
- [ ] 2.3 Confirm the staging joins the dispatch's existing transaction and is committed with it —
      no separate commit, no partial write where a task is staffed and no run exists.
- [ ] 2.4 Confirm the refusal in 2.2 happens before any process is spawned, by reading the order of
      operations in `trigger_agent_directly`. Note where the spawn actually occurs.

## 3. Prove it, including the parts that must not have changed

- [ ] 3.1 **The finding itself.** A completed task, a reviewer that is not its author, dispatched by
      hand: the task is `under_review` and held by the reviewer before the turn begins, and the
      reviewer can reach the outcomes available from review. Watch it fail without phase 2.
- [ ] 3.2 **The flow path travels no extra edge.** Dispatch a flow-staffed review through
      `trigger_agent_directly` and assert the task's status and assignee are unchanged **and that no
      additional transition row was written**. D4 — this is the assertion that makes the idempotency
      claim true rather than assumed.
- [ ] 3.3 **The author is refused before the spawn.** Naming the task's own author returns 403 with
      the guard's wording, and no run row and no process exist afterwards.
- [ ] 3.4 **A request that is never delivered leaves the task alone.** Queue a review entry that the
      turn scheduler declines to deliver (hop budget or token budget) and assert the task's status
      and assignee are untouched. D2 — this is what distinguishes staffing at dispatch from staffing
      at queue time, and without it the two are indistinguishable to the suite.
- [ ] 3.5 **A task that is not awaiting review is refused and keeps its holder.** Dispatch a review
      against an `in_progress` task that has evidence naming a commit — which is reachable, and is
      why `commit_for_task_review` is not a sufficient guard. Assert the refusal, that the assignee
      is untouched, and that no run exists. Without phase 2.2b this test does not merely fail: it
      demonstrates the task being taken from the agent working it.
- [ ] 3.6 **A review held by another reviewer is refused.** Assert the refusal names the holder and
      that the holder is unchanged.
- [ ] 3.7 **Binding still moves nothing.** The `run-task-binding` scenario added by this change:
      staffing precedes binding, and resolving the binding changes neither status nor assignee.
- [ ] 3.8 Mutation-check every guard added or relied on in phase 2, and record each mutation with
      the test that caught it. A mutation that nothing catches is a missing test, not a passing one.

## 4. Drive it

- [ ] 4.1 Live drive against a throwaway project on the trial Hub: a real agent completes a task, a
      second agent is dispatched to review it **by hand**, and the review reaches `approved` with no
      operator bookkeeping in between. Record the run, conversation and task identifiers.
- [ ] 4.2 Drive the refusal live: dispatch the author as its own reviewer and confirm the operator
      sees the 403 and its sentence, and that no run was started.
- [ ] 4.2b Drive D8 live: dispatch a review against a task the agent is still working, and confirm
      the operator sees the refusal and the task stays with its worker.
- [ ] 4.3 Confirm the flow path still works end to end in the same project — one flow-dispatched
      review, unchanged. The idempotency argument is the riskiest part of this change and a unit
      test asserting no extra transition is not the same as watching a flow review complete.
- [ ] 4.4 Record the outcome in `scripts/drive/FINDINGS.md` under F76, including anything that held
      as well as anything that broke, and set its `**Status:**` line.

## 5. Close

- [ ] 5.1 `py -3.11 -m pytest hub/tests/ -q` and `py -3.11 -m pytest tests/ -q` green.
- [ ] 5.2 `ruff` / `black --target-version py311` / `mypy src/` / `npm run lint` clean over the paths
      CI covers.
- [ ] 5.3 `npx openspec validate 2026-08-28-a-review-started-by-hand-can-finish --strict`.
- [ ] 5.4 Sync and archive. Note that the CLI's sync replaces whole requirement blocks, so the
      `MODIFIED` requirement in `run-task-binding` needs checking by hand afterwards.
