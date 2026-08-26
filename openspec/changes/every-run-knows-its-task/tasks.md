# Tasks

Group 1 lands **before** group 2, deliberately. Binding work runs is what makes a mixed turn
dangerous (proposal, "Why now, and why with F66"), so the separation ships before the hazard, not
after it.

## 1. A turn is a review or work, never both (D3, F66)

- [ ] 1.1 Test in `hub/tests/test_turn_scheduler.py`: an agent whose queue holds a review entry
      and a work entry on one conversation is delivered a turn carrying **only** the controlling
      entry's kind, and the other entry is still `queued` afterwards.
- [ ] 1.2 Test: the reverse arrival order gives the reverse outcome — the work entry controls, the
      review waits. This is the case group 1 of `one-answer-to-what-is-happening` left reachable.
- [ ] 1.3 Test: the deferred entry is delivered on the **next** turn, not starved (design risk
      "a review that keeps arriving first could starve the work entry").
- [ ] 1.4 Test: a batch of several work entries and no review is unchanged — still delivered
      together, still bound by the existing ordering rule.
- [ ] 1.5 Test in `hub/tests/test_agent_trigger.py`: `queue_entry_ids` naming both a review entry
      and a work entry, handed to the trigger directly, is refused 409 with both task ids in the
      detail; no run is created and no workspace is prepared.
- [ ] 1.6 Narrow `selected` in `hub/hub/turn_scheduler.py` so the controlling entry's kind decides
      the turn. Keep it beside the existing conversation/hop-depth filter and extend that comment
      block — F5 and F66 are the same defect and should read as such.
- [ ] 1.7 Extend `_review_task_from_entries` (or its caller) in `hub/hub/api/v1/agent_trigger.py`
      to refuse the mixed batch, reusing the existing 409 rather than a second status.
- [ ] 1.8 Update `binding_from_entries`' docstring in `hub/hub/run_task_binding.py`: it currently
      states *"a turn batching work and a review must bind by arrival"*, a case that no longer
      exists. Say what replaced it and why, rather than deleting the sentence.
- [ ] 1.9 Mutation check by name: reverting 1.6 fails 1.1 and 1.2; reverting 1.7 fails 1.5. Record
      the actual failures here, including any that did **not** fail as predicted.

## 2. A flow work firing binds the run it starts (D1, D2)

- [ ] 2.1 Test in `hub/tests/test_scheduler.py`: a firing that claims a task and stages ordinary
      work produces a queue entry carrying `task_id` and **not** `review_task_id`.
- [ ] 2.2 Test: a firing that staffs a review still produces `review_task_id` and **not**
      `task_id` — D2's separation, pinned in both directions.
- [ ] 2.3 Test: the run delivering a work entry is bound to that task, and the task reaches
      `in_progress` without the agent moving it.
- [ ] 2.4 Test: a firing that claims no task starts an unbound run, and that run records no
      divergence when it ends.
- [ ] 2.5 Test: a flow work run ending with no actor transition **is** divergent — the behaviour
      that has never once fired in production.
- [ ] 2.6 Add the `task_id` line to the primary staging path (`hub/hub/scheduler.py:2302` region),
      beside the existing `review_task_id` line and its D9 comment.
- [ ] 2.7 Add the same line to the second staging path (`hub/hub/scheduler.py:2621` region).
- [ ] 2.8 Mutation check by name: removing either line fails 2.1/2.3 and 2.5; setting both fields
      on one entry fails 2.2.

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
