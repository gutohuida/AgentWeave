## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1: explore and propose (2026-09-24, bundle B5)
- [ ] 0.2 R2: independent re-derivation against `spec_service.propose`, `spec_lifecycle.transition`, `spec.py` `propose_document`/`set_phase`, `spec_adoption`, `SpecPhaseBar.tsx`. In particular: run the seven helpers listed in the proposal and record which fixtures are incomplete (a scratch copy that calls `spec_completeness.check` on each fixture payload is enough); confirm no agent-plane path reaches `proposed`/`approved`
- [ ] 0.3 R3: second independent re-derivation; `openspec validate a-document-moves-forward-only-through-its-checks --strict` passes
- [ ] 0.4 The operator approves (APPROVALS.md), including the F113 status change

## 1. Tests first — each fails on today's code unless marked as a control

New file `hub/tests/test_a_document_moves_forward_only_through_its_checks.py`, reusing `_create`, `_submit`, `_document` from `test_spec_documents_api.py`.

- [ ] 1.1 (D3, F207) Create a document, submit nothing, close exploration, `POST /documents/phase?to=proposed` → **409** `document_incomplete` with a non-empty `blocking`; phase still `exploring`. FAILS today (200, `proposed`)
- [ ] 1.2 (D3) Propose a complete document through `propose`, then submit an edit that drops a task (still `sketch`, so it applies), then `phase?to=approved` → 409 `document_incomplete` naming `requirement_without_task`; no `Task` row with that `spec_document_id`. FAILS today (200, tasks created)
- [ ] 1.3 (D2, F113) Incomplete document, exploration open, `propose` → **200**, `blocking` codes include `explore_not_closed` **and** the completeness codes, phase `exploring`. FAILS today (409)
- [ ] 1.4 (D2) Flip `test_spec_documents_api.py::test_a_document_cannot_be_proposed_before_exploration_is_closed` (`:323-335`) to assert 200 and `explore_not_closed` in `blocking`. Comment names this change
- [ ] 1.5 (D3) Control: `test_spec_capability_kind.py` unchanged and passing (illegal moves stay `illegal_transition`)
- [ ] 1.6 (D3) Control: a complete document goes `propose` → `phase?to=approved` → 200 with `tasks_created`, as `test_the_full_operator_path_reaches_approved` does today
- [ ] 1.7 (D3) `phase?to=approved` on a proposed document whose payload was hand-corrupted on disk → 422 `payload_invalid`, phase unchanged
- [ ] 1.8 (D4, UI) `specPhaseBar.test.tsx`: Approve answered 409 with `detail.blocking` renders each finding's `where` and message; a bare 409 message renders via `readableApiError`. FAILS today (nothing rendered)

## 2. The fix

- [ ] 2.1 (D1) `spec_service.phase_blockers`; `propose` rewritten on it
- [ ] 2.2 (D3) `set_phase`: the gated call before `transition`
- [ ] 2.3 Run the seven helpers; make any incomplete fixture complete without weakening an assertion, and list each in the round log
- [ ] 2.4 (D4) `SpecPhaseBar.tsx`; `npm run lint`, `npm test`, build, `py -3.11 scripts/refresh_ui_bundle.py`; commit source and bundle together
- [ ] 2.5 Full `hub/tests/` count recorded; ruff; black `--target-version py311`

## 3. Drive

- [ ] 3.1 Trial Hub: F207's four calls from its entry, verbatim, and record each answer
