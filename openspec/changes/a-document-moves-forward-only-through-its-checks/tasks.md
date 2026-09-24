## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1: explore and propose (2026-09-24, bundle B5)
- [x] 0.2 R2: independent re-derivation against `spec_service.propose`, `spec_lifecycle.transition`, `spec.py` `propose_document`/`set_phase`, `spec_adoption`, `SpecPhaseBar.tsx`. In particular: run the seven helpers listed in the proposal and record which fixtures are incomplete (a scratch copy that calls `spec_completeness.check` on each fixture payload is enough); confirm no agent-plane path reaches `proposed`/`approved`
- [x] 0.3 R3: second independent re-derivation; `openspec validate a-document-moves-forward-only-through-its-checks --strict` passes
- [ ] 0.4 The operator approves (APPROVALS.md), including the F113 status change

## 1. Tests first — each fails on today's code unless marked as a control

New file `hub/tests/test_a_document_moves_forward_only_through_its_checks.py`, reusing `_create`, `_submit`, `_document` from `test_spec_documents_api.py`.

- [ ] 1.1 (D3, F207) Create a document, submit nothing, close exploration, `POST /documents/phase?to=proposed` → **409** `document_incomplete` with a non-empty `blocking`; phase still `exploring`. FAILS today (200, `proposed`)
- [ ] 1.2 (D3) Propose a complete document through `propose`, then submit an edit that drops a task (still `sketch`, so it applies), then `phase?to=approved` → 409 `document_incomplete` naming `requirement_without_task`; no `Task` row with that `spec_document_id`. FAILS today (200, tasks created)
- [ ] 1.3 (D2, F113) Incomplete document, exploration open, `propose` → **200**, `blocking` codes include `explore_not_closed` **and** the completeness codes, phase `exploring`. FAILS today (409)
- [ ] 1.4 (D2) Flip `test_spec_documents_api.py::test_a_document_cannot_be_proposed_before_exploration_is_closed` (`:323-335`) to assert 200 and `explore_not_closed` in `blocking`. Comment names this change
- [ ] 1.5 (D3) Control: `test_spec_capability_kind.py` unchanged and passing (illegal moves stay `illegal_transition`)
- [ ] 1.6 (D3) Control: a complete document goes `propose` → `phase?to=approved` → 200 with `tasks_created`, as `test_the_full_operator_path_reaches_approved` does today
- [ ] 1.7 (D3) `phase?to=approved` on a proposed document whose payload was hand-corrupted on disk → 422 `payload_invalid`, phase unchanged. FAILS today (200); also FAILS if `set_phase` lacks the new `SaveRefusedError` clause (bare 500)
- [ ] 1.7a (D1, R2) Control: `test_spec_task_dependencies.py::test_an_unresolvable_import_is_preserved_and_reported_not_raised` unchanged and passing — approval of a document whose import source was reopened after it was proposed still answers 200. FAILS if `import_not_approved` is kept among the approval blockers
- [ ] 1.9 (D3, operator decision 1) Call `spec_lifecycle.transition(session, document, to_phase=PROPOSED, actor=operator, workspace=ws)` **directly**, on a document created through `POST /documents` (which writes a stub payload, `spec.py:1453-1466`) with exploration closed → `PhaseError` with `code == "document_incomplete"` and a non-empty `exc.blocking`; `document.phase` still `exploring`. Then the same for `APPROVED` on a document set to `proposed` whose payload drops a task. FAILS today (the move happens). This is the test that pins the check to the transition rather than to a route
- [ ] 1.9a (D3) Control: `test_spec_archive.py::test_an_archived_document_has_no_legal_outgoing_transition` (`:214`) and `test_transition_itself_refuses_an_agent_actor_archiving` (`:253-278`, given `workspace=`) unchanged in outcome — the actor and phase-map refusals still precede any file read
- [ ] 1.8 (D4, UI) `specPhaseBar.test.tsx`: Approve answered 409 with `detail.blocking` renders each finding's `where` and message; a bare 409 message renders via `readableApiError`. FAILS today (nothing rendered)

## 2. The fix

- [ ] 2.1 (D1) `spec_service.phase_blockers`; `propose` rewritten to call `transition` and return `exc.blocking` on `document_incomplete`
- [ ] 2.2 (D3) `spec_lifecycle.transition`: required `workspace` keyword; `phase_blockers` called after the phase-map/actor/archive checks, replacing the standalone explore check; `PhaseError.blocking`. `set_phase`: pass `workspace`, add `blocking` to the 409 detail, add the `SaveRefusedError` → 422 clause
- [ ] 2.3 Complete the fixtures R2 found incomplete (add `scope.non_goals` and one criterion per requirement; weaken no assertion): `test_spec_declared_tasks.py` `submit`, `test_spec_task_dependencies.py` `make_document`, `test_task_spec_document_context.py` (helper at `:152`), `test_spec_criteria_reach_the_task.py` (helper at `:207`). Also the two direct `transition()` callers in `test_spec_archive.py`: `:270` passes `workspace=`; `test_first_approved_at_is_set_once_and_survives_a_reopen` (`:281-320`) creates its document with a complete payload in a workspace and passes it (operator review). Then run every spec-document test file; any other new failure is a finding, not a fixture to patch
- [ ] 2.4 (D4) `SpecPhaseBar.tsx`; `npm run lint`, `npm test`, build, `py -3.11 scripts/refresh_ui_bundle.py`; commit source and bundle together
- [ ] 2.5 Full `hub/tests/` count recorded; ruff; black `--target-version py311`

## 3. Drive

- [ ] 3.1 Trial Hub: F207's four calls from its entry, verbatim, and record each answer
