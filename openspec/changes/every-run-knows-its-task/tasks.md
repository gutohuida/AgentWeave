# Tasks

Group 1 lands **before** group 2, deliberately. Binding work runs is what makes a mixed turn
dangerous (proposal, "Why now, and why with F66"), so the separation ships before the hazard, not
after it.

## 1. A turn is a review or work, never both (D3, F66)

- [x] 1.1 Test in `hub/tests/test_turn_scheduler.py`: an agent whose queue holds a review entry
      and a work entry on one conversation is delivered a turn carrying **only** the controlling
      entry's kind. **Corrected during implementation**: the original wording ("the other entry is
      still `queued` afterwards") is false once self-continuation is accounted for —
      `agent_trigger.py` starts the next turn unconditionally the moment one ends with entries
      still queued (its own comment: "a turn ending with queued entries starts the next turn
      without waiting for operator input"), so by the time a test's `_drain()` returns, the
      deferred entry has almost always already been picked up as a turn of its own. Running the
      test as originally written hung the test process indefinitely — not merely failed — because
      the second, self-continued spawn reused a `MagicMock` session whose two-item `read.side_effect`
      was already exhausted by the first turn, and a `StopIteration` raised from a
      `run_in_executor` thread cannot be set on an `asyncio.Future` (`Future.set_exception`
      rejects it), so the awaiting task never resolves. Fixed at the test level (give each spawn a
      fresh session; not a product bug) and reworded to assert what the design doc actually
      promises ("rides the next turn") and what mutation 1.6 actually protects: two **separate,
      un-mixed** turns (distinct `PtySession.spawn` calls, each carrying only its own entry's
      content), not a queue-state snapshot that self-continuation makes too transient to observe.
- [x] 1.2 Test: the reverse arrival order gives the reverse outcome — the work entry controls, the
      review waits. Left as originally written: here self-continuation's retry of the deferred
      review genuinely fails (no evidence-backed reviewable commit in this fixture), so
      `PtySession.spawn` is called once and "please review" legitimately stays `queued` — for a
      different reason than 1.1's fix addresses, documented inline so a future reader does not
      mistake this shape for "self-continuation skips a deferred entry of the other kind".
- [x] 1.3 Test: the deferred entry is not starved (design risk "a review that keeps arriving first
      could starve the work entry"). **Redesigned**: the original test tried to demonstrate this
      via an explicit *second* manual `schedule_agent()` call, on the assumption that the deferred
      entry needs a fresh trigger — false for the same self-continuation reason as 1.1, which makes
      the second call redundant (nothing is left to schedule by then). Rewritten to test the
      literal risk text instead: two review entries (naming the same reviewed task, so they are not
      themselves a mixed batch) arrive ahead of one work entry; both reviews are delivered together
      as the first turn, and the work entry still gets a turn of its own once they drain — proving
      several entries of the other kind ahead of it do not lose it, not just one.
- [x] 1.4 Test: a batch of several work entries and no review is unchanged — still delivered
      together, still bound by the existing ordering rule. Passed as originally written.
- [x] 1.5 Test in `hub/tests/test_agent_trigger.py`: `queue_entry_ids` naming both a review entry
      and a work entry, handed to the trigger directly, is refused 409 with both task ids in the
      detail; no run is created and no workspace is prepared. **Fixed a missing fixture step**: the
      test called `bind_runner("mixed-batch", ...)` without first registering the agent via
      `POST .../session/sync`, so it 404'd ("Agent 'mixed-batch' not found") rather than exercising
      the refusal at all — added the same registration step every sibling test in this file uses.
- [x] 1.6 Narrow `selected` in `hub/hub/turn_scheduler.py` so the controlling entry's kind decides
      the turn. Keep it beside the existing conversation/hop-depth filter and extend that comment
      block — F5 and F66 are the same defect and should read as such.
- [x] 1.7 Extend `_review_task_from_entries` (or its caller) in `hub/hub/api/v1/agent_trigger.py`
      to refuse the mixed batch, reusing the existing 409 rather than a second status.
- [x] 1.8 Update `binding_from_entries`' docstring in `hub/hub/run_task_binding.py`: it currently
      states *"a turn batching work and a review must bind by arrival"*, a case that no longer
      exists. Say what replaced it and why, rather than deleting the sentence.
- [x] 1.9 Mutation check by name, run for real (not assumed from the diff): reverting 1.6 (disabling
      the kind filter in `selected`) failed both 1.1 and 1.2 exactly as predicted
      (`2 failed, 5 warnings in 0.77s`). Reverting 1.7 (disabling the mixed-batch refusal in
      `_review_task_from_entries`) failed 1.5 exactly as predicted. Both mutations were applied via
      `Edit` and reverted via `Edit` back to the exact original text (verified with `git diff
      --stat` unchanged) — **not** via `git checkout --`, which was tried once during this round and
      destroyed the entire uncommitted implementation for `turn_scheduler.py` (it reverts a
      tracked-but-uncommitted file to `HEAD`, not to "before my last edit"); the file was
      reconstructed by hand from the diff read earlier in the session and re-verified against the
      full test file before continuing. Nothing failed to fail as predicted for 1.6/1.7.

## 2. A flow work firing binds the run it starts (D1, D2)

- [x] 2.1 Test in `hub/tests/test_scheduler.py`: a firing that claims a task and stages ordinary
      work produces a queue entry carrying `task_id` and **not** `review_task_id`.
- [x] 2.2 Test: a firing that staffs a review still produces `review_task_id` and **not**
      `task_id` — D2's separation, pinned in both directions.
- [x] 2.3 Test: the run delivering a work entry is bound to that task, and the task reaches
      `in_progress` without the agent moving it.
- [x] 2.4 Test: a firing that claims no task starts an unbound run, and that run records no
      divergence when it ends.
- [x] 2.5 Test: a flow work run ending with no actor transition **is** divergent — the behaviour
      that has never once fired in production.
- [x] 2.6 Add the `task_id` line to the primary staging path (`hub/hub/scheduler.py:2302` region),
      beside the existing `review_task_id` line and its D9 comment.
- [x] 2.7 Add the same line to the second staging path (`hub/hub/scheduler.py:2621` region).
- [x] 2.8 Mutation check by name, run for real: removing the `task_id=` line from the **primary**
      path failed 2.1, 2.3, and 2.5 exactly as predicted (`3 failed, 5 warnings in 2.29s`). Setting
      both fields unconditionally on one entry — tried first against the **second** staging path
      (`hub/hub/scheduler.py`'s `_stage_selection`, ~line 2621) — did **not** fail 2.2
      (`1 passed`): 2.2's fixture (`_flow`, author and critic as distinct agents) turns out to
      staff the reviewer through the **primary** path, not the "additional selection" path the
      task text's line-number hint suggested, so the second path was never exercised. Reapplying
      the identical mutation to the primary path's `task_id=` line failed 2.2 as predicted
      (`1 failed`). **Recorded because it did not fail as predicted on the first attempt** — the
      task text's assumption about which staging path 2.2 exercises was wrong; both lines are
      still correct and both are still covered (2.1/2.3/2.5 pin the primary path directly, 2.2 now
      confirms the primary path's own never-both invariant), but the second path's own "never set
      both" behavior has no dedicated mutation-verified test — worth a follow-up test naming
      `_stage_selection` directly if that path is touched again.
      All four mutations were applied and reverted with `Edit`, verified against `git diff --stat`
      after each revert to confirm an exact restore (see 1.9's note on why `git checkout --` is
      unsafe for this).

**Full-suite ripple, found by running the whole thing rather than trusting the touched-file
scope.** `pytest hub/tests/ -q` after groups 1-2 landed: `3 failed, 3205 passed`. All three
failures were the identical shape (`assert 'in_progress' == 'assigned'`) in tests that predate this
change and were not listed as touched by tasks 2.1-2.8:
`test_flow_chain_end_to_end.py::test_the_chain_runs_a_review_and_then_b_with_no_operator_action`,
`test_flow_fires_a_review_turn.py::test_an_unstaffable_review_does_not_stop_the_flow_doing_other_work`,
and `test_flow_width.py::test_three_startable_tasks_and_one_agent_start_one_and_touch_nothing_else`.
Cause: `run_task_binding.bind_run_to_task` is a **pre-existing** mechanism (already exercised by
direct-`task_id` operator triggers) that advances a bound task past `assigned` to `in_progress` the
moment a run starts on it. Group 2 is the first thing that makes a job/flow-fired queue entry carry
`task_id`, so this pre-existing mechanism now reaches job/flow firings too — these three tests
asserted the *old* gap (a job-fired task sat at `assigned` for its entire run) as if it were the
permanent behaviour, rather than an artifact of `task_id` never having been staged for that path.
Updated all three assertions to `in_progress` with an inline note; each test's own actual point
(which task got claimed, that a stalled loop recovers, that the two untouched tasks in a width test
stay untouched) is unchanged. Re-ran the full suite after the fix: `3208 passed, 84 skipped, 1
xpassed` — 3205 + 3 fixed, 84/1 both matching the pre-existing baseline, nothing else moved.

## 3. One owned answer to "was this a live flow's own work turn" (D4, D5)

- [ ] 3.1 Test the predicate directly, per branch: a live flow's work turn is true; a review turn
      is false; a delegated run is false; an operator-started run is false; a flow whose loop is
      `stopped_at` is false; a flow whose loop is `archived_at` is false; a run whose conversation
      has no `JobRun` is false.
- [ ] 3.2 Implement the predicate as one named function with a docstring stating why it exists —
      that two consumers need the same fact and drift is the defect this change inherits from
      `one-answer-to-what-is-happening`.
- [ ] 3.3 Resolve the flow through `checkpoints.loop_for_conversation`, checking `stopped_at` and
      `archived_at` explicitly rather than treating a non-None loop as live (D5).
- [ ] 3.4 Seam test: the predicate is exercised against a real `Run` and real `Loop` rows, not a
      hand-built fixture. Task 4.9 of `one-answer-to-what-is-happening` initially passed its
      mutation check because every test built its input by hand — do not repeat that.

## 4. A divergence says whether it needs attention (D6)

- [ ] 4.1 Test: a flow work run that moves nothing, on a task still held by the same agent under a
      live loop, emits `run_diverged` at `info`.
- [ ] 4.2 Test: the same run where the task's assignee was cleared emits at `warn`.
- [ ] 4.3 Test: the same run where the run did not end cleanly emits at `warn`.
- [ ] 4.4 Test: a delegated run's divergence is still `warn` — nothing outside the flow path
      changes.
- [ ] 4.5 Test: the durable `RunDivergence` row is byte-identical whichever severity was emitted;
      severity governs the announcement, never the record.
- [ ] 4.6 Test: resolving open divergences emits one `run_divergence_resolved` naming the task and
      the count; moving a task with no open divergences emits nothing.
- [ ] 4.7 Replace the hardcoded `severity="warn"` at `hub/hub/run_divergence.py:738` with the
      derivation, reading the predicate from group 3. Keep the existing comment's reasoning for the
      `warn` case — it is still correct for the case it was written about.
- [ ] 4.8 Emit `run_divergence_resolved` from `resolve_divergences_for_task`, and broadcast it over
      SSE alongside the persisted event, as `run_diverged` already is.
- [ ] 4.9 Register the new event kind wherever event kinds are enumerated for the UI, and confirm
      `EventRow` renders it — do not assume a kind it has never seen renders sensibly.
- [ ] 4.10 Mutation check by name: hardcoding `warn` again fails 4.1; hardcoding `info` fails 4.2
      and 4.3; suppressing the resolution event fails 4.6.

## 5. The flow governs its own work divergence, not `retry` (D7)

- [ ] 5.1 Test: a live flow work run diverging on a task whose policy is `retry` starts **no** run
      and records `policy_applied='flow'`, `outcome='surfaced'`.
- [ ] 5.2 Test: the same task, same policy, but the run was delegated rather than fired by the
      flow — `retry` still applies and still starts a run.
- [ ] 5.3 Test: a live flow work run on a task whose policy is `escalate` **does** escalate, with
      the previous assignee recorded.
- [ ] 5.4 Test: `POLICY_FLOW` is absent from `POLICIES`, so no task can be given it — the same
      assertion group 2 made for `POLICY_REVIEW`.
- [ ] 5.5 Test: a flow work run diverging on a task whose loop has stopped is governed by the
      task's policy again, not by the flow régime. The flow is not going to fire it.
- [ ] 5.6 Add `POLICY_FLOW = "flow"` in `hub/hub/run_task_binding.py` beside `POLICY_REVIEW`, and
      widen the `run_divergences.policy_applied` CHECK in `hub/hub/db/models.py`.
- [ ] 5.7 Migration `0094`, modelled on `0092`. Guard for a missing table as `0033`/`0034` do.
- [ ] 5.8 Bump the head assertions `0093 → 0094` in `hub/tests/test_migrations.py` **and**
      `hub/tests/test_project_persistence.py`.
- [ ] 5.9 Apply the suppression in `hub/hub/run_divergence.py`, reading the predicate from group 3
      rather than re-deriving it.
- [ ] 5.10 Mutation check by name: removing the suppression fails 5.1; applying it unconditionally
      fails 5.2 and 5.3; scoping it to the loop's existence rather than its liveness fails 5.5.

## 6. Drive it live

The trial Hub on port 8010, beta profile, restarted onto this branch. **Confirm the project list,
not only `/health`** — a Hub on a stale database still answers `{"status":"ok"}`.

- [ ] 6.1 Re-measure the baseline before driving: job-origin entries carrying `task_id`, job-
      delivered runs bound, runtime `→ in_progress` transitions. Record the numbers here.
- [ ] 6.2 Drive a flow work firing end to end. Confirm the entry carries `task_id`, the run is
      bound, and the task reaches `in_progress` with no agent action.
- [ ] 6.3 Drive a flow work turn that moves nothing. Confirm the divergence row exists and the
      event arrived at `info`, visible in the activity log with the filter on `all`.
- [ ] 6.4 Drive the same task to completion. Confirm `run_divergence_resolved` arrived and names
      the count.
- [ ] 6.5 Drive a `retry` task under a live flow. Confirm nothing spawned and the row says `flow`.
- [ ] 6.6 Queue a review and a work item for one agent and confirm the delivered turn carries one
      kind, the other stays queued, and the next turn delivers it.
- [ ] 6.7 Re-measure 6.1's figures after the drive and record the delta. This is what tells us
      whether the boundary check now applies where it never did.
- [ ] 6.8 Record every finding in `scripts/drive/FINDINGS.md`, including anything that worked.
- [ ] 6.9 Leave no job enabled and no run alive. State in the handoff what the drive left behind.

## 7. The sweep

- [ ] 7.1 `py -3.11 -m pytest hub/tests/ -q` and `py -3.11 -m pytest tests/ -q`.
- [ ] 7.2 `py -3.11 -m ruff check src/ hub/ tests/` and
      `black --check src/ hub/hub/ hub/tests/ tests/ --target-version py311`.
- [ ] 7.3 `cd hub/ui && npx tsc --noEmit`, `npm run lint`, `npx vitest run`. Rebuild and
      `py -3.11 scripts/refresh_ui_bundle.py` only if any UI source changed under 4.9.
- [ ] 7.4 `npx openspec validate every-run-knows-its-task --strict`.
- [ ] 7.5 Test accounting: name each test file and its before/after count, and the total added.
- [ ] 7.6 Re-read this change's `design.md` against what was built and record every deviation
      inline, as `one-answer-to-what-is-happening` did with its five. A design that no longer
      describes the code is worse than no design.
- [ ] 7.7 Confirm task 4.7 of `one-answer-to-what-is-happening` is now unblocked, and say so in
      that change's `tasks.md`. Do **not** implement it here (D8).
