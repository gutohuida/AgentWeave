## 0. Rounds and decision

- [x] 0.1 R2 (2026-09-24, recorded in `spec-queue/tracks/B2.md`): an independent re-derivation of this proposal against `hub/hub/scheduler.py` (every
      `run_count` write; `_do_fire_job`, `_stage_additional_selections`, `_stage_selection`) and every
      reader of `run_count` in `hub/hub`, `hub/ui/src` and `src/`. Rebuild design's table from `grep`
      before reading it. Record in `spec-queue/tracks/B2.md`
- [x] 0.2 R3 (2026-09-24, recorded in `spec-queue/tracks/B2.md`): a second independent re-derivation. `openspec validate
      a-firing-is-counted-once-however-many-agents-it-starts --strict` passes. both increments (`scheduler.py:3443`, `:3756`) and the badge (`JobCard.tsx:435`) confirmed; no change
- [x] 0.3 (2026-09-28) The operator records D1 in `spec-queue/DECISIONS.md` (bundle B2), as `B2-D1a`
      — a row is a dispatch, citing the same B2 approval `F149-D1b` already used for D1's rename half

## 1. Tests first — each must fail on today's code unless marked as a control

- [x] 1.1 Edit `hub/tests/test_flow_width.py:423-424` (the `rows` case: one firing, two agents):
      assert `run_count == 1`, and replace the comment with one naming this change. Keep
      `len(runs) == 2` and the two distinct conversations. FAILED before 2.1 (`1 == 2`), confirmed
      before the fix was applied
- [x] 1.2 Added `test_two_firings_of_one_flow_count_as_two_however_many_agents_each_started` to the
      same file: two firings of one flow, the first starting two agents (then completed directly)
      and the second one. Asserts `len(runs) == 3`, two distinct `fired_at` values, `run_count == 2`.
      FAILED before 2.1 (`2 == 3`)
- [x] 1.3 Control, extended `test_jobs.py`'s `test_job_history_tracks_runs`: a plain job fired
      twice by `POST /jobs/{id}/run` reads `run_count == 2`, `history` length 2. PASSED before and
      after (D1 does not change repeated-firing counting)
- [x] 1.4 Control, confirmed still passing: `test_board_agent_role.py::test_no_job_run_row_is_written_for_a_declined_firing`
      and `test_a_loop_staffs_the_agent_it_names.py` (`run_count == 0` after a declined firing)
- [x] 1.5 `hub/ui/src/__tests__/jobCard.test.tsx`: `'0 fired'` where it expected `'0 runs'`, plus
      `expect(screen.queryByText(/\bruns\b/)).not.toBeInTheDocument()`; `'1 runs'` → `'1 fired'`;
      added a `run_count: 3` case asserting `'3 fired'`. FAILED before 2.3 (badge still read "runs")

## 2. The fix

- [x] 2.1 `hub/hub/scheduler.py` `_stage_selection`: deleted `job.run_count += 1` and rewrote the
      comment to say `run_count` is not touched there — it counts firings (design D1), and the
      primary path (`_do_fire_job`) already stamped it once for this firing
- [x] 2.2 `hub/hub/schemas/jobs.py`: `run_count: int = Field(description="Firings that queued
      work for at least one agent. A firing that queues work for several agents counts once.")`
- [x] 2.3 `hub/ui/src/components/jobs/JobCard.tsx`: `{job.run_count} fired`. Rewrote the F25
      comment and the one above `RunHistory`'s "0 runs" empty-state usage line at `:362-363` (`0
      fired`) to the firing wording
- [x] 2.4 `make ui` — bundle rebuilt via `scripts/refresh_ui_bundle.py`, committed with
      `hub/ui/src`
- [x] 2.5 Group 1 run individually first (`hub/tests/test_flow_width.py` 27/27,
      `hub/tests/test_jobs.py` + `test_board_agent_role.py` + `test_a_loop_staffs_the_agent_it_names.py`
      78 passed/1 skipped, `jobCard.test.tsx` 19/19) — all passing. Then the full suites, on the
      uncommitted tree over `c1d7486` (2026-09-28, interactive session): `py -3.11 -m pytest
      hub/tests -n auto -q` with `claude` stripped from PATH — 5110 passed, 86 skipped, 0 failed;
      `py -3.11 -m pytest tests/ -q` — 553 passed, 3 skipped; `npx vitest run` — 168 files, 1735
      passed
- [x] 2.6 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`, `cd hub/ui
      && npm run lint`, `npx tsc --noEmit`, `mypy src/` — clean (2026-09-28)
- [x] 2.7 `scripts/drive/t_row11_loop.py`: both verdicts (`:230-234`ish, `:313-318`ish) re-pointed
      from `run_count == len(hist)` to `run_count == len({h.get("fired_at") for h in hist})`, labels
      reworded to "run_count matches the number of firings (distinct `fired_at`)", with a comment
      naming this change and the one-agent-loop caveat

## 3. Drive it

- [x] 3.1 On a trial Hub from source (fresh port and profile; never `:8000`), a flow with two
      startable tasks and two Haiku agents: press Run once. `GET /jobs/{id}` reads `run_count: 1`
      and its history holds two rows sharing `fired_at`. Disable the job afterwards. Done
      2026-09-28 on `:8051`, profile `drive0928firing`, `scripts/drive/d0928_firing_counted_once.py`:
      an approved document seeded two pending tasks; one press started agents `one` and `two` (two
      measured `claude-haiku-4-5-20251001` turns); `GET /jobs/{id}` read `run_count=1` with two
      `completed` history rows both at `2026-09-28T08:05:44.101721Z`. Job disabled and archived
