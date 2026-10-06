## 0. Review

- [x] 0.1 One grounded review round over proposal, design and the three spec deltas: every claim
  re-read at its cited `file:line` or checked by something run. Findings are folded in or rejected
  with a reason, in a short "Review round" section of `design.md`. Done 2026-10-05 night: R1-R5
  folded in (R1: D5 read lifecycle state, not coverage), one rejected, F497 filed.

## 1. Acceptance drive first (design: Acceptance drive)

- [x] 1.1 Read-only count on `:8000` (`mode=ro`, `~/.agentweave/hub/data/agentweave.db` --
  `.claude/reference/hubs.md` names this as the database `:8000` actually opens, not the `live`
  profile): **6 tasks**, all in project `proj-03b9c6a6c37a` (LoopEngine) -- statuses `pending` x2,
  `completed` x2, `under_review` x1, `revision_needed` x1 -- serve one of **7 requirements** whose
  current-digest evidence (`digest` match, `review_state` grouping per `requirement_coverage._state`;
  no open `requirement_drift` rows exist in this database, so drifting never applies) is every row
  `rejected`. Measured 2026-10-05 night.
- [x] 1.2 Drive D (`testbed/drive-slices/drive_d.py`, stub provider on `:8010`, `stub_provider.py`
  extended with `DRIVE-D-TASK` and `DRIVE-D-EVIDENCE <id> <task>` markers) written and run
  2026-10-05 night: fails at (a) exactly as expected --
  `{"code": "task_too_coarse", "where": "tasks[0]", "message": "'t1' names 5 requirements, over
  the ceiling of 3 ..."}`. (b)-(e) are written against the design's table but not yet run to
  completion -- the run stops at the first `fail()`, by design, and the ceiling still blocks (a).
  Rerun after 2.1/2.2 (below): (a) and (b) now PASS. (c) FAILs, but on a drive-script bug, not a
  product gap -- `stub_provider.py`'s `DRIVE-D-EVIDENCE` handler passes the document-local key
  (`r1`) straight to `record_evidence`'s `identifier`, which needs the project-level identifier
  `submit_spec_document` actually minted (`FR-1`, from its response's `identifiers` map); the Hub
  correctly 404s "this project has no requirement r1" (`agent_actions.py:1205`). Group 3 (3.1)
  must fix the stub to use the `identifiers` map, or (c)-(e) can never run.

## 2. The ceiling (D1)

- [x] 2.1 Tests first: a task naming five requirements is proposable; a requirement served by no
  task is still refused. Rewrote `test_spec_completeness.py:133` (now
  `test_a_task_naming_five_requirements_is_proposable`), `:146` (now
  `test_a_requirement_served_by_no_task_is_still_refused`). Done 2026-10-05 night, confirmed red
  (five-requirements test failed on `task_too_coarse`) before 2.2.
- [x] 2.2 Removed `MAX_REQUIREMENTS_PER_TASK` and the `task_too_coarse` finding from
  `spec_completeness.py`; reworded the charter line -- actual path is
  `hub/hub/data/charters/spec.md:101` (`tasks.md`/`design.md`'s `data/charters/spec.md` has no such
  file; confirmed by search), not `data/charters/spec.md`. Done 2026-10-05 night.
  `pytest hub/tests/test_spec_completeness.py -q`: 24 passed.

## 3. The rejected block at every rigor (D2, D4)

- [x] 3.1 Tests first, against the transition (operator route and the agent/tool path), one per
  scenario of *Approval is refused while a gated requirement is unverified* that this change adds:
  sketch, contract and gate each refuse a rejected requirement; new accepted evidence lifts it; a
  rejected contract requirement is blocking and not reported; a sketch task with unverified,
  non-rejected requirements still approves. Added to `test_requirement_gate.py` (six tests, both
  routes covered by `test_the_sketch_rejection_refuses_on_the_agent_plane_too`). Done 2026-10-06.
- [x] 3.2 Rewrote `test_approval_refuses_unaccepted_evidence.py:625` (rejected evidence now refuses
  via `blocking`, not an approve-and-skip) and `test_task_integration.py:510` (the rejected commit
  needs a second, accepted, no-op piece of evidence before approval can be asked for at all) as D4
  states. Done 2026-10-06.
- [x] 3.3 The rejected step in `requirement_gate.evaluate`, above the early return, with the loop
  skipping what it already blocked (`_linked_requirements` added so the step and the enforced loop
  share one query). `pytest hub/tests/test_requirement_gate.py
  hub/tests/test_approval_refuses_unaccepted_evidence.py hub/tests/test_task_integration.py -q`:
  92 passed. `ruff check` and `black --check --target-version py311` clean on all four touched
  files. Done 2026-10-06.
  **Note:** this code and its tests were already written, uncommitted, when this iteration started
  -- a prior firing did 3.1-3.3 but was cut off before verifying or committing. This iteration
  verified the suite, then drove it.
  **Stub fixes, not product code** (both found this iteration, re-running drive D against the
  reused trial project): `stub_provider.py`'s `DRIVE-D-EVIDENCE` handler now caches the project
  identifier and document path `submit_spec_document`'s response carried (`LAST_IDENTIFIERS`,
  `LAST_PATH` -- a later run is a fresh conversation that never sees that response itself, and a
  repeatedly-reused project leaves more than one approved document naming `FR-1`, so `record_evidence`
  needs both the real identifier and `document` to disambiguate). `drive_d.py`'s own two evidence-decision
  calls were missing the route's `/project` segment and sent `"reject"`/`"accept"` where the API
  wants `"rejected"`/`"accepted"` -- fixed both. Reran on `:8010` (Hub restarted with
  `MY_F490_KEY` so it ran group 3's new code, stub restarted after each fix): **(a)-(d) now PASS**
  end to end -- the sketch-rigor rejected block fires for real, not only in the unit tests. **(e)
  FAILs** (`policy digest is (None,), expected non-null`) exactly as expected: D3, which (e) is
  about, is group 4's job, not yet built.

## 4. The policy a sketch approval records (D3)

- [x] 4.1 Tests first: a sketch task serving requirements records a digest; a task serving none
  records null. `test_requirement_gate.py:905` (`test_an_ungated_approval_records_no_policy`) split
  into `test_a_task_linking_nothing_records_no_policy` (a task created with no `requirement_ids` at
  all, no document submitted — the null case D3 leaves alone) and
  `test_a_sketch_task_serving_requirements_records_a_digest` (the existing `_document`/`_linked_task`
  shape, asserting a non-null digest). Also reworded
  `test_a_sketch_with_unverified_non_rejected_requirements_still_approves`'s docstring, which cited
  the old test name for a point D3 changes. Confirmed red before 4.2: stashed the implementation
  change and reran just the new digest test — failed `assert None is not None`; unstashed, reran
  green. Done 2026-10-06.
- [x] 4.2 `requirement_gate.evaluate` now builds the policy list from every linked document
  (`by_all_document`, already computed for D2's rejected step), not only the enforced ones — a
  `sketch` document contributes its requirements' `(identifier, state, integration, rigor)` to the
  digest the same way `contract`/`gate` do, but adds no `blocking`/`reported`/`diagnostics` entry
  (gated by a new `enforces = rigor != spec_rigor.SKETCH` flag the loop already had the rigor to
  compute). The early return moved from `if not enforced` to `if not rows`, so a task linking only
  `sketch` documents no longer short-circuits to a null digest, while a task linking nothing still
  does. `pytest hub/tests/test_requirement_gate.py hub/tests/test_approval_refuses_unaccepted_evidence.py
  hub/tests/test_task_integration.py hub/tests/test_approval_waits_for_the_turn.py
  hub/tests/test_spec_completeness.py -q`: 130 passed. `ruff check` and `black --check
  --target-version py311` clean on both touched files. Done 2026-10-06.
  **Drive.** Restarted the trial Hub on `:8010` (stale process from iter 5, predating this group's
  code; `DATABASE_URL` + `MY_F490_KEY=fake-c1b-drive-not-a-key`, no `--reload`) and the stub on
  `18496`. Reran `testbed/drive-slices/drive_d.py`: **(a)-(e) all PASS**, (e) reporting a non-null
  policy digest (`b6ac17363effa635...`) — D3 fires end to end, not only in the unit tests. Stopped
  the stub afterward; left the trial Hub running. Removed one untracked `spec/changes/umber-yeti/`
  directory the drive's project wrote into the working tree (same precedent as groups 2-3).

## 5. The card (D5)

- [x] 5.1 Tests first (vitest), in `taskRequirementLinks.test.tsx`: rewrote "gives a chip whose
  requirement has rejected evidence the rejected tone" to set coverage per document (`setCoverage`,
  a module-level `coverageByPath` map a new `useSpecCoverageMany` mock reads) and give both links
  the *same* `requirement_links[].state` (`active`) — so the old implementation's premise (reading
  that field) could not pass; added a pending/neutral-tone test (a retired link with no coverage
  row) and the five-vs-four summary tests (`task-requirement-summary-<id>`). Confirmed red: 3 new
  tests failed, 9 pre-existing passed, before 5.2. Done 2026-10-06.
- [x] 5.2 Added `useSpecCoverageMany(paths)` to `api/spec.ts` (`useQueries`, one query per path,
  the exact `['project', projectId, 'specCoverage', path]` key `useSpecCoverage` already uses, so
  it reads the same cache and the same invalidations). `useRequirementChips` now resolves each
  linked document's coverage through it and maps `CoverageEntry.state` to a `tone`
  (`verified`/`pending`/`rejected`/`neutral`); `rejected` stays as a boolean (`tone === 'rejected'`)
  for the existing CSS class. `TaskCard.tsx` applies the tone as a class modifier (`neutral` adds
  none, matching the old look) and renders a `task-requirement-summary-<id>` line above the chips
  once there are more than four, counting verified/rejected/open (everything else). `latestRejectionReason`
  (unused anywhere outside the hook — grepped) was dropped rather than kept dead.
  Two other test files mocking `@/api/spec` without the new export broke
  (`taskCountIsTheLedgersOwn.test.tsx`, `tasksBoardFilter.test.tsx`, both empty-document fixtures —
  just needed the export added) and one relied on the old `has_rejected_evidence`-driven tone
  (`taskBoardConsideredStates.test.tsx`) — updated to a coverage fixture. `npx vitest run`: 1871
  passed (179 files). `npx eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0`
  and `npx tsc --noEmit`: clean. `npm run build` then `py -3.11 scripts/refresh_ui_bundle.py`:
  bundle refreshed, stamp recorded. No drive: the design's acceptance table (Drive D) does not cover
  D5, and no backend route changed. Done 2026-10-06.

## 6. Close

- [x] 6.1 `pytest hub/tests/ -q`: **6779 passed, 93 skipped** (2619.53s). `pytest tests/ -q`:
  **567 passed, 3 skipped** (75.42s). Both green at `b30e7dc` (the tip this closing work started
  from). Done 2026-10-06.
- [x] 6.2 Restarted the trial Hub on `:8010` fresh (`DATABASE_URL` + `MY_F490_KEY`, no `--reload`,
  killed the 1:19:58am process first so there was no doubt it was running every group's code) and
  the stub provider on `18496`. Reran `testbed/drive-slices/drive_d.py` end to end: **(a) PASS, (b)
  PASS, (c) PASS, (d) PASS, (e) PASS — policy digest `b6ac17363effa635...`** — `DRIVE D PASSED`.
  Stopped the stub afterward; left the trial Hub running. Removed one untracked
  `spec/changes/onyx-hydra/` directory the drive's project wrote (same precedent as groups 2-4).
  `scripts/backlog_page.py --check`: current, nothing moved. Done 2026-10-06.
- [x] 6.3 `spec-queue/METRICS.md` row appended. Done 2026-10-06.
