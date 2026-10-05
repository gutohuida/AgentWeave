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

- [ ] 3.1 Tests first, against the transition (operator route and the agent/tool path), one per
  scenario of *Approval is refused while a gated requirement is unverified* that this change adds:
  sketch, contract and gate each refuse a rejected requirement; new accepted evidence lifts it; a
  rejected contract requirement is blocking and not reported; a sketch task with unverified,
  non-rejected requirements still approves. Ask what each route returns when the gate refuses.
- [ ] 3.2 Rewrite `test_approval_refuses_unaccepted_evidence.py:625` and `test_task_integration.py:510`
  as D4 states.
- [ ] 3.3 The rejected step in `requirement_gate.evaluate`, above the early return, with the loop
  skipping what it already blocked.

## 4. The policy a sketch approval records (D3)

- [ ] 4.1 Tests first: a sketch task serving requirements records a digest; a task serving none
  records null. Rewrite `test_requirement_gate.py:905`.
- [ ] 4.2 The digest covers every served requirement at every rigor.

## 5. The card (D5)

- [ ] 5.1 Tests first (vitest): each chip carries its **coverage** state, from the document's
  coverage response, not `requirement_links[].state`; five requirements show the count; four show
  none.
- [ ] 5.2 `useRequirementChips` (reads `useSpecCoverage` per linked document) and `TaskCard.tsx`;
  `npm run lint`; refresh the bundle; commit
  `hub/ui/src` and `hub/hub/static/ui` together.

## 6. Close

- [ ] 6.1 Full suites (`pytest hub/tests/ -q`, `pytest tests/ -q`), with counts and a sha here.
- [ ] 6.2 Drive D passes (a)-(e) on `:8010`.
- [ ] 6.3 A `spec-queue/METRICS.md` row: tier, times, and which stage caught each defect.
