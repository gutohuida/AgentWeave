## 0. Rounds and decision

- [x] 0.1 R2 (2026-09-24, recorded in `spec-queue/tracks/B2.md`): an independent re-derivation. `grep -n '"run_id"' hub/hub/scheduler.py hub/hub/api/v1/jobs.py`
      and every other persist or broadcast of a `JobRun` id; every reader of `run_id` out of event
      data in `hub/hub`, `hub/ui/src` and `scripts/drive`. Rebuild design's reader table before
      reading it. Record in `spec-queue/tracks/B2.md`
- [x] 0.2 R3 (2026-09-24, recorded in `spec-queue/tracks/B2.md`): a second independent re-derivation. `openspec validate
      run-id-in-an-event-always-names-a-run --strict` passes. the ten sites and `run_job`'s answer re-grepped; the one reader (`agents.py:883-891`) and the MCP pass-through confirmed; no change
- [ ] 0.3 The operator records D1's second half in `spec-queue/DECISIONS.md`

## 1. Tests first — each must fail on today's code

New file `hub/tests/test_run_id_names_a_run.py`.

- [x] 1.1 Fire a plain job through `POST /jobs/{id}/run` with the spawn patched out (reuse `_no_spawn`
      from `test_a_task_nothing_will_move_holds_nobody.py`). The answer has `job_run_id` equal to the
      new `JobRun` id and no `run_id`. The persisted `job_fired` event's data has `job_run_id` and no
      `run_id`. Capture `sse_manager.broadcast` (monkeypatch) and assert the same of the broadcast
      payload. Record that it FAILS today
- [x] 1.2 `job_run_skipped`: fire a job whose agent is skipped by `_job_agent_skip_reason`. The
      persisted payload has `job_run_id` and no `run_id`. Record that it FAILS today
- [x] 1.3 `job_run_failed`: patch `JobScheduler._fire_job_internal` to raise, press Run (500), and
      read the event `_record_job_run_failure` wrote. `job_run_id`, no `run_id`. Record that it FAILS
      today
- [x] 1.4 The stream rule: after 1.1, every persisted event for the project whose data carries a
      non-null `run_id` names an existing `Run`. Record that it FAILS today (the `job_fired` row)
- [x] 1.5 A wide flow firing (reuse `test_flow_width.py`'s `rows` staging): both `job_fired` events,
      the primary's and the extra selection's, carry `job_run_id`. Record that it FAILS today

## 2. The fix

- [x] 2.1 `hub/hub/scheduler.py`: rename the key at every site in the proposal's table
- [x] 2.2 `hub/hub/api/v1/jobs.py`: `_record_job_run_failure`'s payload and `run_job`'s success answer
      (`:1510`); rename `run_job`'s local `run_id` to `job_run_id` so the next reader is not misled
- [x] 2.3 `hub/ui/src/api/jobs.ts:252`: the response type. `npm run lint`; refresh the bundle only if
      the build output changes
- [x] 2.4 Run group 1; full `py -3.11 -m pytest hub/tests/ -q` and `cd hub/ui && npm test -- --run`,
      counts inline
- [x] 2.5 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`, clean

## 3. Drive it

- [ ] 3.1 On a trial Hub from source (never `:8000`), fire a Haiku job, then read the project's event
      history: the `job_fired` row names `job_run_id`, and the `run_started` row beside it names the
      real run under `run_id`. Disable the job afterwards
