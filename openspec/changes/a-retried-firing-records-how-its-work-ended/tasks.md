## 0. Rounds and decision

- [x] 0.1 R2 (2026-09-24, recorded in `spec-queue/tracks/B2.md`): an independent re-derivation against `hub/hub/api/v1/agent_trigger.py` (every call of
      `finalize_job_run_for_conversation` and `return_run_entries`, and `withdraw_refused_entry`),
      `hub/hub/inbound_queue.py` (`return_run_entries`, `_withdraw_if_queued`), `hub/hub/turn_scheduler.py`
      (the give-up), `hub/hub/api/v1/inbound_queue.py` (the withdrawal route), `hub/hub/run_reconciliation.py`
      and `hub/hub/scheduler.py`. Rebuild design's two tables from `grep` before reading them. Check in
      particular: is there any other writer that moves a job-origin entry out of `queued`? Is autoflush
      really on for the session at each site? Record in `spec-queue/tracks/B2.md`
- [x] 0.2 R3 (2026-09-24, recorded in `spec-queue/tracks/B2.md`): a second independent re-derivation. `openspec validate
      a-retried-firing-records-how-its-work-ended --strict` passes. Bounded D4 (the pinned case stays a
      control), MODIFIED the stranded-firing requirement, added D6 (loops refresh) and tasks 1.11, 1.12, 2.7
- [ ] 0.3 The operator records D1 in `spec-queue/DECISIONS.md` and answers design Open Questions 1,
      2 and 3. No task below starts before D1 is recorded as *a row is a dispatch*

## 1. Tests first — each must fail on today's code unless marked as a control

New file `hub/tests/test_a_retried_firing_records_how_its_work_ended.py`. Reuse `_make_job` from
`test_run_reconciliation.py`. Seed rows directly, as that file does; each case names the
conversation `conv-<case>` and writes the job's queue entry with `origin_type="job"`.

- [ ] 1.1 (F147, crash) The agent has a runner bound (R3: D4 keeps the row open only then, or under a
      refusal); `JobRun` `in_progress` on C; `Run` `running`, `pid=None`, on C; a job entry
      `delivered` in that run at `delivery_attempts=0`. Call `reconcile_interrupted_runs()` then
      `reconcile_stale_job_runs()`. Assert the entry is `queued` and the `JobRun` is still
      `in_progress`. Then insert a second `Run` on C, deliver the entry to it, and call
      `conclude_dispatches_for_conversation(db, C, "completed")` after marking that run `completed`:
      the `JobRun` reads `completed`. Record that the first assertion FAILS today (`failed`)
- [ ] 1.2 (R1 find, no crash) Same seed; call `_record_run_failure_tail(...)` with a `RuntimeError`.
      Assert the entry is `queued` at attempts 1 and the `JobRun` is `in_progress`. Record that it
      FAILS today (`failed`)
- [ ] 1.3 The last attempt: the entry at `delivery_attempts=2`; `_record_run_failure_tail`. Assert the
      entry is `withdrawn` with its `abandoned_reason`, and the `JobRun` is `failed` with
      `error_summary` equal to that reason. Record that it FAILS today on the summary (`None`)
- [ ] 1.4 (F147, `.first()`) On C, a `JobRun` `in_progress`; an `interrupted` `Run` with the
      **earlier** `started_at`, and a `running` `Run` with this test process's pid and the later
      `started_at`. Insert the `running` one **first**, so the test cannot pass by insertion order.
      `reconcile_stale_job_runs()` leaves the row `in_progress`. FAILS today, deterministically (R2:
      `ix_runs_conversation_started` orders the unordered query by `started_at`, so `.first()` is
      the interrupted run whatever the insertion order)
- [ ] 1.5 Scheduler give-up: a job entry `queued` at `delivery_attempts=2` for an agent whose turn
      the scheduler refuses at request level non-transiently (reuse the refusal fixture in
      `test_a_delivery_attempt_is_counted_where_attempted*` or equivalent), with `JobRun`
      `in_progress` on its conversation. `schedule_agent(...)`. Assert `withdrawn` and `JobRun`
      `failed` with the abandonment reason. Record that it FAILS today (`in_progress`: nothing on
      the give-up path concludes a dispatch). The seeded state is reachable in production only once
      2.2 lands, because today the earlier attempt's run end already wrote `failed`; that is exactly
      why D3 is needed, and why this test is written against the seed rather than a live sequence
- [ ] 1.6 Operator withdrawal: `JobRun` `in_progress`, a queued job entry. `DELETE` the entry through
      the route. Answer 200; `JobRun` `stopped`. Record that it FAILS today (`in_progress`)
- [ ] 1.7 The withdrawal's conclusion raises: patch `conclude_dispatches_for_conversation` to raise.
      The route still answers 200 with the entry `withdrawn`; the `JobRun` stays `in_progress`; a log
      record names the job run. Record that it FAILS today (the function does not exist)
- [ ] 1.8 Controls, PASS today and must keep passing: every test in `test_run_reconciliation.py`,
      notably `:168` (no run at all → `failed`), `:197` (dead run, no entry → `failed`), `:236` (live
      run → `in_progress`); and the two refusal cases in `test_a_held_agent_is_busy.py` that read
      `reconcile_stale_job_runs` (`test_a_held_firing_survives_a_restart`,
      `test_a_firing_whose_reset_passed_while_the_hub_was_down_survives_a_restart`)
- [ ] 1.8a Control (R3's bounded D4): `test_a_held_agent_is_busy.py:732-739`,
      `test_a_firing_for_an_agent_with_no_runner_and_no_refusal_still_fails` keeps passing unchanged.
      Only if the operator answers Open Question 3 *yes* now: invert and rename it instead, and record
      that the inverted form FAILS today
- [ ] 1.11 (D4 scope, control) 1.1's seed with the returned entry `origin_type="operator"` instead of
      `"job"`: after the startup pair the row reads `failed` (an operator's input does not hold a
      dispatch open). Passes today and must keep passing
- [ ] 1.12 (D6, UI) In `useSSE`'s tests: a `queue_entry_withdrawn` frame and a `queue_entry_abandoned`
      frame each invalidate `['project', pid, 'loops']`. Record that both FAIL today
- [ ] 1.8b `test_scheduler.py:1289-1328` (spawn fails): await every background run until
      `agent_trigger._background_runs` is empty (the retries are scheduled by the re-drain after the
      first snapshot), then assert the entry `withdrawn` and the `JobRun` `failed` with the
      abandonment reason as `error_summary`. Add an intermediate assertion after the first attempt
      only: `in_progress`. Record that the intermediate assertion FAILS today (`failed`)
- [ ] 1.9 The operator's follow-up: a job entry delivered in run R on C, plus an operator entry
      (`origin_type="operator"`) `queued` on C. R completes. The `JobRun` reads `completed`. Control
      today (passes), must keep passing — it pins D1's *job input* scope
- [ ] 1.10 Two open rows on one conversation (a `resume` job): two `JobRun`s `in_progress` on C, one
      run delivers both job entries and completes. Both read `completed`. Record that it FAILS today
      (the older stays `in_progress`)

## 2. The fix

- [ ] 2.1 `hub/hub/scheduler.py`: replace `finalize_job_run_for_conversation` with
      `conclude_dispatches_for_conversation(session, conversation_id, status, *, reason=None)`
      (design D1). Two `EXISTS` subqueries; `UPDATE` every `in_progress` row on the conversation.
      Docstring names this change and D1's decision. Follow the rename in
      `hub/tests/test_scheduler.py:46` (and its unit test at `:1333-1373`),
      `hub/tests/test_flow_holds_the_loop_requirements.py:162`, and the comments that name the old
      function (`db/models.py:1400`, `run_reconciliation.py:238`, `scheduler.py:1013`, `:3435`,
      `:3553`, `:3645`, `hub/ui/src/hooks/useSSE.ts:477-479`; a comment-only UI edit needs no
      bundle refresh)
- [ ] 2.2 `hub/hub/api/v1/agent_trigger.py`: at `:2050`, `:2193`, `:3065`, `:2521`, `:3159` move the
      call below `return_run_entries`, same session, before the commit (design D2). Delete the
      `if refusal is None:` guard at `:2521`; keep and generalise its comment. At the three failure
      sites pass the abandoned job entry's reason where `abandoned_for_run` names one
- [ ] 2.3 Conclude on withdrawal (design D3): `turn_scheduler.py` give-up (after its commit, per
      abandoned job entry) and the
      route at `api/v1/inbound_queue.py:259`. Each wraps the call so a raise is logged and does not
      change what the writer answers
- [ ] 2.4 `hub/hub/run_reconciliation.py` `reconcile_stale_job_runs`: *any running run* as an `EXISTS`;
      queued **job** input keeps the row open only where its agent has a runner bound or
      `_waits_on_a_refusal` (narrowed to job-origin entries) holds; rewrite the docstring's D10
      paragraph (design D4, bounded by R3)
- [ ] 2.5 Run group 1; every row passes. `py -3.11 -m pytest hub/tests/ -q`, count recorded inline;
      any other moved assertion is named and explained
- [ ] 2.6 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`, clean
- [ ] 2.7 `hub/ui/src/hooks/useSSE.ts`: invalidate the loops query on `queue_entry_withdrawn` and
      `queue_entry_abandoned` (design D6). `cd hub/ui && npm test -- --run` and `npm run lint`; `make ui`;
      commit `hub/ui/src` and `hub/hub/static/ui` together

## 3. Drive it

- [ ] 3.1 Re-run `scripts/drive/t_row19_crash_job.py` on a trial Hub from source (fresh port and
      profile; never `:8000`; Haiku). The job's history reads `completed` for the crashed firing
      once the retry completes. Record the three rows F147 recorded (`runs` ×2, `job_runs` ×1). Update
      the harness's assertion that expected `failed` (F147: *"the second one asserts the defect as the
      expected outcome"*)
- [ ] 3.2 Disable every job created
