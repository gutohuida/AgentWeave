## 1. The busy guard

- [ ] 1.1 Test: firing a loop five times while its agent has a running `Run` creates zero
      `InboundQueueEntry` rows and zero `JobRun` rows, and leaves every task's status and assignee
      unchanged. This is the measured failure — it currently produces five of each.
- [ ] 1.2 Test: a firing after the agent's run ends claims normally, proving the guard refuses rather
      than disables.
- [ ] 1.3 Add the already-running check to `_do_fire_job`, before the claim and before `new_entry`.
      Same shape as `_job_agent_skip_reason`, which is already in that function.
- [ ] 1.4 Return without writing a `JobRun` — the `JobRun` created earlier in the function must not
      be persisted for this path (design D4). Confirm the early return does not leave a partial row.
- [ ] 1.5 Verify `_prune_job_history` is unaffected and the loop's job stays enabled and scheduled.

## 2. Tick recording

- [ ] 2.1 Test: firing repeatedly against one stalled queue produces exactly one `JobRun` whose tick
      count equals the number of refused firings.
- [ ] 2.2 Test: a stall whose reason text changes starts a new `JobRun` rather than incrementing the
      previous one.
- [ ] 2.3 Test: a loop that alternates between real firings and long refusal periods still shows the
      real firings in the most recent records — the last-ten view stays useful at a fast tick rate.
- [ ] 2.4 Migration adding the tick counter to `JobRun`. Guard for a missing table as `0033`/`0034`
      do; default reads as one for pre-existing rows.
- [ ] 2.5 Bump the head assertions in `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py`.
- [ ] 2.6 Implement the increment-or-append rule in `_do_fire_job`'s stall path: same job, most recent
      run is a stall, same reason -> increment; otherwise append.
- [ ] 2.7 Expose the count on `JobRunResponse` so the history endpoints can render it.

## 3. Handoff detection

- [ ] 3.1 Test each branch of design D1/D2 independently: completed with a `review` message; completed
      with no message; completed with a message of another type; `under_review` moved by another
      agent; `under_review` moved by the completing agent; `under_review` moved by the operator.
- [ ] 3.2 Test that the derivation reads only persisted rows — no agent output is consulted.
- [ ] 3.3 Implement the derivation as one function: `Message` by `task_id` and `type == "review"`,
      plus `TaskTransition.actor_agent` for the move into `under_review` compared against the agent
      recorded moving it to `completed`.
- [ ] 3.4 Reuse `_agent_that_completed`'s ordering discipline — by `sequence`, not `created_at`, for
      the reason its own docstring gives.

## 4. The shared claimability decision

- [ ] 4.1 Test: for a queue holding an un-handed-off finished task, `_batch_loop_summaries`' current
      item and `_do_fire_job`'s decision agree. This is human-only check 13.1 made mechanical, and
      the drift it guards against is the one `_loop_queue_order` records.
- [ ] 4.2 Implement the decision as one function returning what this firing should do — claim,
      re-brief, refuse-stalled, or proceed-empty.
- [ ] 4.3 Call it from `_do_fire_job` and from `_batch_loop_summaries` (`hub/hub/api/v1/jobs.py:170`),
      importing rather than restating, matching the existing convention in that module.
- [ ] 4.4 Confirm `completed` is NOT added to `CLAIMABLE_LOOP_TASK_STATUSES` (design D3) — assert it
      in a test, since widening the tuple is the obvious wrong fix.

## 5. The re-brief

- [ ] 5.1 Test: a loop whose queue holds an un-handed-off `completed` task and a claimable `pending`
      task re-briefs about the first and leaves the second `pending` and unassigned.
- [ ] 5.2 Test: a re-brief changes no task's status or assignee.
- [ ] 5.3 Test: a finished task WITH a review in flight produces no re-brief.
- [ ] 5.4 Implement the re-brief branch in `_do_fire_job`: compose a briefing naming the task and
      stating it was completed without being sent for review, and claim nothing else.
- [ ] 5.5 Confirm the briefing does not name a reviewer and does not send a message on the agent's
      behalf.

## 6. Bounding the re-brief

- [ ] 6.1 Test: a task at the maximum re-brief count produces no further re-brief.
- [ ] 6.2 Test: two un-handed-off tasks in one loop carry independent counts.
- [ ] 6.3 Test: a task that acquires a review in flight has its count reset, so a later
      `revision_needed` -> `in_progress` -> `completed` cycle starts from zero.
- [ ] 6.4 Migration adding the per-task re-brief counter, with the same missing-table guard.
- [ ] 6.5 Implement increment, bound check, and reset-on-review-in-flight.

## 7. Surfacing exhaustion

- [ ] 7.1 Test: reaching the maximum notifies the operator, and the notification names the task and
      the attempt count.
- [ ] 7.2 Test: reaching the maximum leaves the job enabled and scheduled, and records no loop stop
      reason.
- [ ] 7.3 Test: after the operator approves the exhausted task, the next firing claims the next
      claimable task — proving recovery needs no further operator action.
- [ ] 7.4 Test: a project whose only agent is the loop's executor reaches exhaustion and surfaces,
      with no special-case code path.
- [ ] 7.5 Implement the surfacing, following the existing event and SSE pattern the stop path uses.

## 8. Retroactive specification of what already shipped

- [ ] 8.1 Confirm the `agent-loops` delta's stall-refusal requirement matches the behaviour
      `_loop_stall_reason` already implements, and that its scenarios pass against the shipped code
      before this change adds anything.
- [ ] 8.2 Confirm `revision_needed`'s presence in `CLAIMABLE_LOOP_TASK_STATUSES` is covered by an
      existing test and needs no new requirement here.

## 9. Agent-verifiable checks

- [ ] 9.1 `pytest hub/tests/ -v` passes, with the three pre-existing `test_pty_runner` environment
      failures unchanged and no new failures.
- [ ] 9.2 `openspec validate loop-notices-and-reacts` reports valid.
- [ ] 9.3 `ruff check hub/` and `black --check hub/` pass on every touched file.
- [ ] 9.4 A firing refused for any reason creates no `InboundQueueEntry` — asserted directly, not
      inferred from a `JobRun` status.
- [ ] 9.5 The claim decision function has exactly two call sites, asserted by a source scan in the
      style of `hub/tests/test_task_transitions.py`'s existing origin scan.

## 10. Human-only verification

These cannot be established by an agent and must be checked by the operator against a running Hub.

- [ ] 10.1 With a loop mid-turn, confirm the loop board does not flicker or show the loop as idle
      while firings are being refused.
- [ ] 10.2 Confirm a stalled loop's history entry reads sensibly as its tick count climbs, rather than
      looking like a stuck row.
- [ ] 10.3 Confirm the re-brief briefing is one an agent actually acts on — the wording is a judgement
      no test can make.
- [ ] 10.4 Confirm the exhaustion notice is noticeable without being alarming, and that it is clear
      the loop has not died.
- [ ] 10.5 Drive a real two-agent handoff end to end and confirm no re-brief is issued when the agent
      does hand off correctly.

## 11. User test guide

- [ ] 11.1 Write the operator-facing guide covering: creating a loop, watching a firing claim work,
      deliberately completing a task without handing off, observing the re-brief, observing
      exhaustion, and resolving it by approving the task.
- [ ] 11.2 Include how to tell the three refusal reasons apart from the loop's own history, and what
      each one means about what the loop is waiting for.
