## 0. Rounds and decision

- [ ] 0.1 R2: an independent re-derivation of this proposal against `hub/hub/scheduler.py` (every
      `run_count` write; `_do_fire_job`, `_stage_additional_selections`, `_stage_selection`) and every
      reader of `run_count` in `hub/hub`, `hub/ui/src` and `src/`. Rebuild design's table from `grep`
      before reading it. Record in `spec-queue/tracks/B2.md`
- [ ] 0.2 R3: a second independent re-derivation, not starting from R2's notes. `openspec validate
      a-firing-is-counted-once-however-many-agents-it-starts --strict` passes
- [ ] 0.3 The operator records D1 in `spec-queue/DECISIONS.md` (bundle B2). No task below starts
      before it, and none starts if D1 is answered otherwise than *a row is a dispatch*

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 Edit `hub/tests/test_flow_width.py:423-424` (the `rows` case: one firing, two agents):
      assert `run_count == 1`, and replace the comment with one naming this change. Keep
      `len(runs) == 2` and the two distinct conversations. Record that it FAILS today (2)
- [ ] 1.2 Add to the same file: two firings of one flow, the first starting two agents and the
      second one (complete the first firing's tasks between them, or stage a third task that becomes
      startable). Assert three `JobRun` rows, two distinct `fired_at` values, and `run_count == 2`.
      Record that it FAILS today (3)
- [ ] 1.3 Control, PASSES today and must keep passing: a plain job fired twice by `POST
      /jobs/{id}/run` reads `run_count == 2` (`test_jobs.py:419-421` covers one press; extend it or
      add beside it)
- [ ] 1.4 Control, PASSES today and must keep passing: `test_board_agent_role.py:346` (a declined
      firing does not count) and `test_a_loop_staffs_the_agent_it_names.py:336`
- [ ] 1.5 `hub/ui/src/__tests__/jobCard.test.tsx:391-412`: expect `'0 fired'` where it expects
      `'0 runs'`, and add `expect(screen.queryByText(/\bruns\b/)).not.toBeInTheDocument()` against the
      badge row. Add a case `run_count: 3` renders `'3 fired'`. Record that both FAIL today

## 2. The fix

- [ ] 2.1 `hub/hub/scheduler.py` `_stage_selection`: delete `job.run_count += 1` (`:3756`) and
      rewrite the comment at `:3753-3755` to say the counter counts firings (this change, D1) and
      the row counts the dispatch
- [ ] 2.2 `hub/hub/schemas/jobs.py:213`: `run_count: int = Field(description="Firings that started
      at least one agent. A firing that starts several agents counts once.")`
- [ ] 2.3 `hub/ui/src/components/jobs/JobCard.tsx:435`: `{job.run_count} fired`. Rewrite the F25
      comment (`:436-442`) and the one at `:362-363` to the firing wording
- [ ] 2.4 `make ui` (or `scripts/refresh_ui_bundle.py`); commit `hub/ui/src` and
      `hub/hub/static/ui` together
- [ ] 2.5 Run group 1; every row passes. `py -3.11 -m pytest hub/tests/ -q` and `cd hub/ui && npm
      test -- --run` with counts recorded inline. Any other moved assertion is named and explained
- [ ] 2.6 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`, `cd hub/ui
      && npm run lint`, clean

## 3. Drive it

- [ ] 3.1 On a trial Hub from source (fresh port and profile; never `:8000`), a flow with two
      startable tasks and two Haiku agents: press Run once. `GET /jobs/{id}` reads `run_count: 1`
      and its history holds two rows sharing `fired_at`. Disable the job afterwards
