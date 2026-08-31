## 1. Reproduce before repairing

- [ ] 1.1 Add `hub/tests/test_a_review_nobody_is_doing.py` with a test that builds the population
  directly: a loop, one task in `under_review` with a non-author assignee, no run and no queue entry.
  Assert today's behaviour — the decision is `in_flight` and `stall_reason` is `None` — and watch it
  **fail after** the repair, not before. Written first, run first, recorded as red.
- [ ] 1.2 A second case in the same file for the author-wedged row (`t_f154_wedged_review.py` LANE
  5): same assertions, assignee is the agent that completed the work, no agent-walked transition in
  its history. It must reach the same outcome as 1.1 by the same rule.

## 2. The predicate

- [ ] 2.1 Add `tasks_with_a_turn_pending_or_running(session, project_id)` to
  `hub/hub/run_task_binding.py`, beside `tasks_held_by_a_running_turn`, returning `task_id -> agent`
  for tasks with a running bound run **or** an `InboundQueueEntry` in state `queued` naming the task
  in `task_id` or `review_task_id` (design D2, D3).
- [ ] 2.2 Docstring states why it is a second function rather than a widening of
  `tasks_held_by_a_running_turn`, naming that function's own two-callers-two-questions note.
- [ ] 2.3 Unit tests for the predicate alone: running run counts; queued entry counts by `task_id`;
  queued entry counts by `review_task_id`; `withdrawn` entry does **not** count; delivered entry does
  not count on its own; a task with neither is absent from the map.

## 3. The decision

- [ ] 3.1 Ask the predicate once before the walk in `decide_firing`, beside `held`, `free` and
  `running` (`scheduler.py:1283-1291`).
- [ ] 3.2 In the `WITH_REVIEWER` branch, keep appending to `in_flight` unchanged (design D1), and
  additionally record the task in a walk-local list of reviews nobody is doing when the predicate
  does not name it.
- [ ] 3.3 Choose `DECISION_IN_FLIGHT` only where at least one `in_flight` member is named by the
  predicate. Otherwise fall through to the stall path.
- [ ] 3.4 The fall-through carries a sentence naming the task and the agent, promoted to
  `stall_reason` by the existing F64 rule and emitted through `_emit_review_unstaffed`
  (design D4). It states neither that the work is being done nor that a later firing will pick it up.
- [ ] 3.5 Comment at the branch records what `_cannot_staff` still feeds and why the row stays in it
  — `task_attribution` and F63's `held` — so the next reader does not "tidy" it out.

## 4. Guard what must not move

- [ ] 4.1 Test: a genuinely busy flow, every candidate held by a running turn, still decides
  `in_flight` and records no stall (F23).
- [ ] 4.2 Test: a review staffed but still `queued` for its agent reports no stall (design D2's
  window).
- [ ] 4.3 Test: the board's capacity for the wedged row is still `held`, not `assigned` — asserted
  through `task_attribution.attribute` with the staffing this firing produces, which is where D1's
  tripwire would fire (F63).
- [ ] 4.4 Test: nothing on this path reassigns the task or fires another agent (`agent-flows`'
  "no substitution" scenario).

## 5. Validate and drive

- [ ] 5.1 `openspec validate --strict a-review-nobody-is-doing-is-named`.
- [ ] 5.2 `ruff check src/ hub/ tests/`; `black --check --target-version py311 src/ hub/hub/
  hub/tests/ tests/`; `mypy src/`.
- [ ] 5.3 The Hub suite. Record the numbers rather than "green".
- [ ] 5.4 **Drive it.** Restart the Hub on 8011 from the implementing branch, then re-run
  `scripts/drive/t_f154_wedged_review.py`. Its LANE 2 and LANE 5 assertions currently pass *because*
  the defect is present, so they must be updated to assert the new sentence — update them and say in
  the harness what changed, so the file records the fix rather than hiding it.
- [ ] 5.5 The drive's pass condition: the firing names the task and the agent on both the
  reviewer-wedged and the author-wedged row, `stall_reason` is non-null on both, the board still
  reads `held`, and no job is left enabled.
- [ ] 5.6 Record the outcome in `scripts/drive/FINDINGS.md` under F154 with the commit that closed
  it, and note that F154's `agent_capacity` claim was wrong (round 1) so the ledger carries the
  correction.

## 6. Ordering

- [ ] 6.1 Do not sync or archive this change into `openspec/specs/` before it has driven (5.4–5.5).
  A firing sentence is exactly the kind of thing that reads right and cannot fire.
