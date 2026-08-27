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

- [x] 3.1 Test the predicate directly, per branch: a live flow's work turn is true; a review turn
      is false; a delegated run is false; an operator-started run is false; a flow whose loop is
      `stopped_at` is false; a flow whose loop is `archived_at` is false; a run whose conversation
      has no `JobRun` is false. All seven in `hub/tests/test_flow_divergence_regime.py`'s
      `test_a_live_flows_work_turn_is_true` through `test_a_conversation_with_no_jobrun_is_not_a_flow_work_turn`.
- [x] 3.2 Implemented as `is_live_flow_work_turn(session, run)` in `hub/hub/run_divergence.py`,
      with a docstring stating exactly this: read by both D6 and D7, never re-derived at either
      site.
- [x] 3.3 Resolves the flow through `checkpoints.loop_for_conversation`, checking `stopped_at` and
      `archived_at` explicitly (D5) — confirmed by mutation 3's third case below.
- [x] 3.4 Seam test: every fixture in `test_flow_divergence_regime.py` builds real `AIJob`/`Loop`/
      `JobRun`/`Run` rows (`_flow_context`, `_flow_work_run`, `_flow_review_run`,
      `_unbound_flow_conversation_run`, `_orphan_job_conversation_run`) rather than a hand-built
      stand-in for "this is a live flow" — the exact gap task 4.9 of
      `one-answer-to-what-is-happening` left, named in this task's own text.

## 4. A divergence says whether it needs attention (D6)

- [x] 4.1 Test: `test_a_healthy_flow_work_divergence_is_announced_at_info`.
- [x] 4.2 Test: `test_the_same_shape_with_the_assignee_cleared_is_warn`.
- [x] 4.3 Test: `test_the_same_shape_with_an_unclean_ending_is_warn`.
- [x] 4.4 Test: `test_a_delegated_divergence_is_still_warn`.
- [x] 4.5 Test: `test_the_divergence_row_does_not_carry_severity_at_all` — asserts `severity` is
      not even a column on `RunDivergence`, and that every tracked column matches across an
      `info`-announced and a `warn`-announced row.
- [x] 4.6 Test: `test_resolving_open_divergences_names_the_task_and_the_count` — one event on the
      transition that closes the open row, nothing on a later transition with nothing left open.
- [x] 4.7 `hub/hub/run_divergence.py`'s hardcoded `severity="warn"` (the line the task named as
      `:738` had drifted to `:805` by the time this group started, from group 2's insertions)
      replaced with the derivation: `info` only when `flow_work_turn` and `task.assignee ==
      run.agent` and `run.status == "completed"`, else `warn`. Checked against the task's
      *post-policy* state deliberately — an escalation branch runs before this line and may have
      just moved `task.assignee` off `run.agent`, and that is not the quiet case either.
- [x] 4.8 `resolve_divergences_for_task` now emits `run_divergence_resolved` (payload
      `{task_id, count}`, `severity="info"`) and broadcasts it over SSE, only when `open_rows` is
      non-empty. Required a `commit: bool = True` parameter on `utils.persist_event` (default
      preserves all 72 other call sites): this function is reached from inside
      `task_transition_service.apply_transition`, before that function's own caller commits —
      `apply_transition`'s own docstring states "the caller commits", and `persist_event`'s
      unconditional commit would have landed that still-in-flight write early. `commit=False`
      here; `sse_manager.broadcast` needed no equivalent change, since its payload is already in
      memory rather than a re-read of the database.
- [x] 4.9 Registered in `hub/ui/src/lib/eventSummary.ts` — the one place event kinds are
      enumerated for the timeline (`EventRow.tsx` itself has no per-kind switch; it renders purely
      by severity). Pinned by two new cases in `hub/ui/src/__tests__/eventSummary.test.ts`
      (singular/plural count wording). UI rebuilt (`npm run build` +
      `scripts/refresh_ui_bundle.py`) and committed alongside the source change.
- [x] 4.10 Mutation check by name, run for real: hardcoding `severity = "warn"` failed 4.1 exactly
      as predicted (`assert 'warn' == 'info'`). Hardcoding `severity = "info"` failed both 4.2 and
      4.3 exactly as predicted (`assert 'info' == 'warn'`, both). Suppressing the resolution event
      (`if False and open_rows:`) failed 4.6 exactly as predicted (`assert [] == [{'count': 1, ...}]`).
      All three mutations applied and reverted with `Edit`, verified against `git diff --stat`
      after each revert.

## 5. The flow governs its own work divergence, not `retry` (D7)

- [x] 5.1 Test: `test_a_live_flows_retry_task_records_the_flow_regime_and_starts_nothing`.
- [x] 5.2 Test: `test_the_same_policy_off_the_flow_path_still_retries`.
- [x] 5.3 Test: `test_a_live_flows_escalate_task_still_escalates`.
- [x] 5.4 Test: `test_policy_flow_can_never_be_set_on_a_task`.
- [x] 5.5 Test: `test_a_stopped_flows_retry_task_is_governed_by_the_task_policy_again`.
- [x] 5.6 `POLICY_FLOW = "flow"` added in `hub/hub/run_task_binding.py` beside `POLICY_REVIEW`
      (documented as deliberately absent from `POLICIES`, same reasoning). CHECK constraint in
      `hub/hub/db/models.py` widened to `('surface', 'retry', 'escalate', 'review', 'flow')`.
- [x] 5.7 Migration `0094_flow_divergence_regime.py`, modelled on `0092`: `batch_alter_table` table
      recreation, the `{run_divergences, projects, tasks} <= tables` guard from `0033`/`0034`'s
      shape, downgrade rewrites `flow` back to `retry`.
- [x] 5.8 Head assertions bumped `0093 → 0094` in both `hub/tests/test_migrations.py`
      (`HEAD_REVISION`) and `hub/tests/test_project_persistence.py`. Both files' full suites still
      green (78 passed, 1 skipped).
- [x] 5.9 Applied in `evaluate_run_end`'s non-review branch: `if policy == POLICY_RETRY and
      flow_work_turn:` overrides to `policy = POLICY_FLOW`, `outcome = OUTCOME_SURFACED`, no
      response queued — reading the group-3 predicate computed once, above the review/work split,
      not re-derived here.
- [x] 5.10 Mutation check by name, run for real: removing the suppression (`if False and
      policy == POLICY_RETRY and flow_work_turn:`) failed 5.1 exactly as predicted (`assert 'retry'
      == 'flow'`). Applying it unconditionally (`if True:`) failed both 5.2 and 5.3 exactly as
      predicted (`assert 'flow' == 'retry'`, `assert 'flow' == 'escalate'`). Scoping the predicate
      to the loop's existence rather than its liveness (`return loop is not None`) failed 5.5 as
      predicted, and also failed two of group 3's own predicate tests (the `stopped_at`/
      `archived_at` branches) — a mutation that broke more than the task named, recorded rather
      than narrowed to match the task text. All mutations applied and reverted with `Edit`,
      verified against `git diff --stat` after each revert.

**Full-suite check, run for real rather than assumed from the touched-file scope (the standing
lesson from groups 1-2's ripple).** `pytest hub/tests/ -q`: `3227 passed, 84 skipped, 1 xpassed`
(3208 baseline + 19 in this group's new/extended files — `test_flow_divergence_regime.py`'s 18 plus
one added case elsewhere in the touched-file set) — **zero failures, no ripple** into any
pre-existing test. `pytest tests/ -q` (CLI suite): `440 passed, 3 skipped`, unrelated to this
change and unaffected. Also run and clean: `ruff check src/ hub/ tests/`,
`black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` (one file needed
reformatting, applied), `mypy src/`, `npx tsc --noEmit`, `npm run lint`, `npx vitest run` (138
files, 1402 tests, all passing — the "Error: boom" console output during the run is
`ErrorBoundary.test.tsx` deliberately throwing), `npx openspec validate every-run-knows-its-task
--strict`.

## 6. Drive it live

The trial Hub on port 8010, beta profile, restarted onto this branch. **Confirm the project list,
not only `/health`** — a Hub on a stale database still answers `{"status":"ok"}`.

**DRIVEN 2026-08-27, iteration 8.** Restarted the trial Hub from `hub/` onto this branch (killed
stale PID 4300, which had been serving sha `7219090`; the new process ran migration `0093 -> 0094`
on startup, confirming the beta database is current). `GET /api/v1/projects` confirmed all 5
expected projects including `proj-5e960453` (never given a turn). Drove against `proj-18e5d4e0`
(ledger-stress), its pre-existing "Ledger flow" job (`job-bdea22bb0308`, live `Loop`
`loop-e4b864459808`, `stopped_at`/`archived_at` both `NULL`).

- [x] 6.1 Baseline **before** driving: 61 job-origin (`origin_type='job'`) entries, **0** carrying
      `task_id`; 55 runs carrying `task_id`; runtime (`actor_kind='run'`) `→ in_progress`
      transitions: **20** (not design.md's stale 10 — that figure predates this session's own
      groups 1-2 landing and being driven once already in iteration 6; superseded here per the
      design's own stated discipline).
- [x] 6.2 Enabled the job, fired it via `POST /jobs/{id}/run`. New entry `entry-8abc48705d4a`
      carried `task_id='task-e6b05093'` (the job's own pre-existing `assigned` task) — the first
      job-origin entry in this database's history to do so. Bound run `run-f0d830489053` recorded
      `task_id='task-e6b05093'`; `task_transitions` shows `assigned -> in_progress` with
      `actor_kind='run'`, `run_id` set, no operator or agent action.
- [x] 6.3 That same run ended without moving the task (still `in_progress`). `run_divergences`
      recorded `div-c6184053c187` (`policy_applied='surface'`, `outcome='surfaced'`); the matching
      `event_logs` row (`run_diverged`) carries **`severity='info'`** — D6's derived severity,
      confirmed live, not just in the unit suite. Visible via `GET .../events/history` (the
      severity-agnostic history endpoint; `filter=all` is the UI's own default query param, not a
      server-side gate — confirmed the row is present with no filter applied).
- [x] 6.4 The job's own next cron tick (5 min later, `run-34d1d409409f`) picked the same task back
      up and completed it. `run_divergence_resolved` fired with `{"task_id": "task-e6b05093",
      "count": 2}` — naming the count, and resolving not only 6.3's divergence but a second,
      unrelated one from 2026-08-24 that predates this change entirely (both share one task and
      neither had been resolved before now).
- [x] 6.5 Created a fresh task (`task-4928038eba7e`), `divergence_policy='retry'`, assigned to
      `builder`, in the live loop, instructed to make no change and not call `update_task`. Fired
      the job; the run ended with the task still `assigned/in_progress` and unmoved.
      `run_divergences` recorded **`policy_applied='flow'`** (not `retry`) — D7's suppression,
      confirmed live. Confirmed nothing auto-spawned for this task afterward (exactly one `runs`
      row exists for it).
- [x] 6.6 Constructed a real reviewable task (`task-60d1d8183feb`, linked to requirement FR-1,
      builder produced a real commit + evidence) so a genuine review entry could be queued. Fired
      two `POST /agent/trigger` calls for `critic` back-to-back — one `review_task_id`, one
      `task_id` (reusing an already-approved task, since only the entry's *kind* matters for this
      check) — while `critic` was idle. The review entry was accepted and spawned the turn
      immediately (`run-be3fc325f1d2`, `delivered_in_run_id` set); the work entry landed
      `state='queued'` behind it. After the review turn ended, the deferred work entry's
      `delivered_in_run_id` updated to the very next run (`run-30ab9bd030f5`) with no further
      operator action — confirming D3 live: one turn, one kind, the deferred entry rides the next
      turn exactly as designed.
- [x] 6.7 Baseline **after**: 71 job-origin entries (**10** new from this drive), **8** carrying
      `task_id` (0 -> 8; the other 2 new job-origin entries are review-staffing entries, which
      carry `review_task_id` instead of `task_id` by design). Runs carrying `task_id`: 55 -> 70.
      Runtime `→ in_progress` transitions: 20 -> **28** (+8, matching the 8 newly-bound job-origin
      work entries 1:1). This is the delta the group exists to produce: the boundary the design
      measured as *structurally unreachable* (0/61) now applies exactly where the change intended.
- [x] 6.8 Recorded in `scripts/drive/FINDINGS.md` (F69) — everything above, plus what held: no
      mixed turn occurred despite two concurrent live loops on the same agent roster (`builder`
      appeared in both `loop-e4b864459808` and `loop-a5613d9f7723`'s queues during the drive), and
      a pre-existing, unrelated staffing stall (a task naming `critic` as its own declared
      reviewer after critic did the work itself, `scheduler.py:1050`'s `unresolved` rung) was hit
      and resolved as a real operator would — by approving the task directly — which is itself
      evidence the ladder's terminal rung behaves as documented under real, un-staged conditions.
- [x] 6.9 Job `job-bdea22bb0308` disabled at the end (confirmed `SELECT id FROM ai_jobs WHERE
      enabled=1` returns zero rows). Self-continuation and one peer-triggered message (`critic` ->
      `builder`, `origin_type='agent'`) kept the conversation draining for several more minutes
      after the job was disabled — expected per the standing `dead_ends` note, not a new finding —
      until `runs`/`inbound_queue_entries` both showed nothing running and nothing queued. **Left
      behind in `proj-18e5d4e0`**: four new tasks (`task-4928038eba7e` — probe, `in_progress`,
      unresolved surfaced divergence, harmless and intentionally left as evidence of 6.5;
      `task-c0bd47157c19` — real one-line comment commit, `completed`, no requirement link so no
      evidence, never reviewed; `task-60d1d8183feb` — real one-line comment commit,
      `approved`, requirement FR-1, fully reviewed by 6.6's drive; `task-e6b05093` — the job's own
      pre-existing task, now `approved`, operator-approved directly after a stale staffing stall).
      No cleanup performed beyond disabling the job, per the same reasoning `ledger-stress`'s other
      accumulated drive evidence has always been left in place for.

## 7. The sweep

- [x] 7.1 `py -3.11 -m pytest hub/tests/ -q` and `py -3.11 -m pytest tests/ -q`. CLI: `440 passed,
      3 skipped` (22.80s), unaffected by this change. Hub: `3227 passed, 84 skipped, 1 xpassed`
      in 1033s (17m13s — the whole sweep's other checks ran concurrently in the foreground while
      this was in the background, which is the likely cause of it running longer than the ~11-18
      min this suite has measured at before; zero tests failed either way).
      `grep -ci "FAILED\|ERROR"` on the full log: `0`.
- [x] 7.2 `py -3.11 -m ruff check src/ hub/ tests/`: `All checks passed!`.
      `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`: `494 files would be
      left unchanged`. `py -3.11 -m mypy src/`: `Success: no issues found in 22 source files`.
- [x] 7.3 `cd hub/ui && npx tsc --noEmit`: clean, no output. `npm run lint`
      (`eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0`): clean, no
      output. `npx vitest run`: `138 files passed (138)`, `1402 tests passed (1402)` — the `Error:
      boom` console spew is `ErrorBoundary.test.tsx` deliberately throwing, not a failure. No UI
      source changed since group 5's `eventSummary.ts`/`.test.ts` (already committed in `e948770`
      and rebuilt then), but `npm run build` + `py -3.11 scripts/refresh_ui_bundle.py` were run
      again anyway as a real check rather than an assumption — bundle refreshed and stamp
      re-recorded clean, `git diff --stat hub/hub/static/ui` shows only the stamp's own timestamp
      field changed, confirming no drift.
- [x] 7.4 `npx openspec validate every-run-knows-its-task --strict`: `Change
      'every-run-knows-its-task' is valid`.
- [x] 7.5 Test accounting, before = collected count at `c0e4cba` (the commit immediately before
      group 1-2's implementation commit `d23b9c6`), after = collected count at the tip of this
      group. Counted with `pytest <file> --collect-only -q` on both, not assumed from diff size:
      - `hub/tests/test_turn_scheduler.py`: 0 → 4 (new file, group 1).
      - `hub/tests/test_agent_trigger.py`: 42 → 43 (+1, group 1's mixed-kind `queue_entry_ids`
        test 1.5).
      - `hub/tests/test_scheduler.py`: 54 → 59 (+5, group 2's binding tests 2.1-2.5).
      - `hub/tests/test_flow_divergence_regime.py`: 0 → 18 (new file, groups 3-5).
      - `hub/tests/test_flow_chain_end_to_end.py`: 5 → 5 (unchanged count — group 1's 3-test
        ripple fix corrected existing assertions, added none).
      - `hub/tests/test_flow_fires_a_review_turn.py`: 8 → 8 (unchanged count, same ripple fix).
      - `hub/tests/test_flow_width.py`: 26 → 26 (unchanged count, same ripple fix).
      - `hub/tests/test_migrations.py`: 72 → 72 (unchanged count — only the head assertion's
        string literal moved from `0093` to `0094`).
      - `hub/tests/test_project_persistence.py`: 7 → 7 (same kind of head-assertion bump).
      - **Total added: 28** (1 + 5 + 4 + 18), matching group 3-5's own log entry ("+19 new" for
        groups 3-5 alone: 18 in `test_flow_divergence_regime.py` + 1 in `eventSummary.test.ts`,
        which is a UI file outside this Python accounting) plus groups 1-2's +9 (4 + 5, with
        1.5's +1 folding into `test_agent_trigger.py`'s count above).
- [x] 7.6 Done in `design.md` itself — a "Built, with no behavioural deviation" note added after
      the Risks section, confirming all eight decisions landed as designed, plus a correction of
      two citations that drifted as line numbers moved (`run_divergence.py:738` → `:813` for D6's
      replaced hardcode; `scheduler.py:2621` → `:2630` for D1's second staging path). Neither
      citation drift changed what either decision says — recorded as the ordinary kind of drift
      this document's own citations warn about, not a design error.
- [x] 7.7 Confirmed and recorded in `openspec/changes/one-answer-to-what-is-happening/tasks.md`'s
      task 4.7: groups 1-5 wrote the binding this task was waiting on, and group 6 measured it
      live (job-origin entries carrying `task_id`: 0/61 → 8/71 on the same beta database that
      task's own figures were measured against). The fallback removal itself stays out of this
      change (D8) and is Q3 of the current autonomous queue.
