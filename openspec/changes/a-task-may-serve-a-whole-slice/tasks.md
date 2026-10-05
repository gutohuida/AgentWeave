## 0. Review

- [ ] 0.1 One grounded review round over proposal, design and the three spec deltas: every claim
  re-read at its cited `file:line` or checked by something run. Findings are folded in or rejected
  with a reason, in a short "Review round" section of `design.md`.

## 1. Acceptance drive first (design: Acceptance drive)

- [ ] 1.1 Read-only count on `:8000` (`mode=ro`): tasks not yet approved that serve a requirement
  whose current-digest evidence is all rejected. Record the number here; it is who the
  behaviour change reaches.
- [ ] 1.2 Drive D (`testbed/drive-slices/drive_d.py`, stub provider on `:8010`) written, and run
  before the build: it fails at (a) with `task_too_coarse`.

## 2. The ceiling (D1)

- [ ] 2.1 Tests first: a task naming five requirements is proposable; a requirement served by no
  task is still refused. Rewrite `test_spec_completeness.py:133`, `:146`.
- [ ] 2.2 Remove `MAX_REQUIREMENTS_PER_TASK` and the `task_too_coarse` finding; reword
  `data/charters/spec.md:101`.

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

- [ ] 5.1 Tests first (vitest): each chip carries its state; five requirements show the count; four
  show none.
- [ ] 5.2 `useRequirementChips` and `TaskCard.tsx`; `npm run lint`; refresh the bundle; commit
  `hub/ui/src` and `hub/hub/static/ui` together.

## 6. Close

- [ ] 6.1 Full suites (`pytest hub/tests/ -q`, `pytest tests/ -q`), with counts and a sha here.
- [ ] 6.2 Drive D passes (a)-(e) on `:8010`.
- [ ] 6.3 A `spec-queue/METRICS.md` row: tier, times, and which stage caught each defect.
