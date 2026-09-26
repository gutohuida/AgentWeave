## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1: explore and propose (2026-09-24, bundle B5)
- [x] 0.2 R2: independent re-derivation against `SpecCoverageBar.tsx`, `SpecDocumentPanel.tsx`, `api/spec.ts` (`useSpecEvents`), `api/tasks.ts` (every task-scoped query key), `spec.py` list/decision routes, `agent_actions.py` decision route, `sse.py`. Confirm the list route's order; confirm neither decision route broadcasts today; answer design Open Question 2
- [x] 0.3 R3: second independent re-derivation; `openspec validate the-coverage-bar-takes-the-evidence-decision-it-asks-for --strict` passes
- [x] 0.4 The operator approves (APPROVALS.md)

## 1. Tests first — each fails on today's code unless marked as a control

- [x] 1.1 (D3, backend) `hub/tests/test_evidence_decision_is_announced.py`: capture broadcasts by patching `hub.api.v1.spec.sse_manager.broadcast` (and `hub.api.v1.agent_actions.sse_manager.broadcast`) with a recording coroutine, the pattern in `test_a_flow_names_what_it_cannot_staff.py:997`, decide a piece through `POST /spec/evidence/{id}/decision`, assert one `spec_updated` event carrying the evidence id. The same through the agent plane with a granted agent. FAILS today (no event)
- [x] 1.1a (D3, R3) With the F358 change's test 1.14 staging (an approved task waiting, integration raising), the decision still broadcasts one `spec_updated` carrying the evidence id and answers 200. FAILS if the broadcast reads `evidence.id` after the integration call
- [x] 1.2 (D1, UI) `hub/ui/src/__tests__/evidencePieces.test.tsx`: mock `GET /spec/evidence?identifier=FR-1&document=…` returning **two awaiting pieces oldest first** (the route's order). Assert both render with summary, actor, `commit_sha[:12]` and branch, and that the *latest* label is on the **second** (the most recently produced). Reversing the fixture must fail the label assertion. FAILS today (component absent)
- [x] 1.3 (D1) Accept posts `{"decision":"accepted","reason":""}` to `/spec/evidence/<id>/decision` for the clicked piece
- [x] 1.3a (D1, operator decision 3) An awaiting piece whose footprint is `{kind: 'git', commit_sha}` renders the *may merge commit … into main* sentence beside Accept; a piece with a `paths` footprint, and an accepted piece, do not. FAILS today (component absent)
- [x] 1.4 (D1) Reject is disabled with an empty reason; with a reason it posts `{"decision":"rejected","reason":…}`
- [x] 1.5 (D2) A 403/409 response renders the detail message beside the piece; the piece still shows Accept
- [x] 1.6 (D2) A row with `recording_run_live: true` renders disabled buttons and the *still being recorded* sentence
- [x] 1.7 (D1) `specCoverage.test.tsx`: a row with `evidence_count: 0` has no Evidence toggle; with `evidence_count: 2`, it has one. Existing assertions in that file keep passing (control)
- [x] 1.8 (D3) The mutation's success invalidates `specCoverage`, `specEvidence`, and the prefixes `['project', pid, 'task']` and `['project', pid, 'tasks']` (spy on `queryClient.invalidateQueries`)

- [x] 1.9 (D4, backend; announce/flush order pinned by source, not an `_execute_run` run — a stub-runner run was not built) With broadcasts captured as in 1.1: a run records evidence through the agent plane, then its `_execute_run` `finally` runs (the pattern existing `_execute_run` tests use with a stub runner). Assert exactly one `spec_updated` carrying `{"run_ended": run_id}`, and that when it is sent `run_liveness.run_is_live(run_id)` is already `False` (the recording coroutine asserts it at call time). Same for `_execute_codex_appserver_run`. FAILS today (no event)
- [x] 1.9a (D4) Control: a run that recorded no evidence ends with no `spec_updated`; `runs_that_recorded_evidence` is empty after either run ends
- [x] 1.10 (D4, UI) `useSpecEvents`: a `spec_updated` with neither `path` nor `evidence` (`{run_ended}`) invalidates `specCoverage` and `specEvidence` and throws nothing

## 2. The fix

- [x] 2.1 `api/spec.ts`: `EvidencePiece` type (the `_evidence_view` shape plus optional `recording_run_live`), `useSpecEvidence(path, identifier, enabled)` keyed `['project', pid, 'specEvidence', path, identifier]`, `useDecideEvidence()`; `useSpecEvents` also invalidates `specEvidence`
- [x] 2.2 `components/spec/EvidencePieces.tsx` per design D1/D2
- [x] 2.3 `SpecCoverageBar.tsx`: an *Evidence (n)* toggle on rows with `evidence_count > 0`, mounting `EvidencePieces`
- [x] 2.4 `spec.py` and `agent_actions.py` decision routes: broadcast `spec_updated` after integration
- [x] 2.4a (D4) `run_liveness.runs_that_recorded_evidence`; the agent-plane record route adds the run id after its commit; both `finally` blocks discard it synchronously beside the registry clear and, after `outside_writes.flush()`, broadcast `spec_updated {"run_ended": run_id}` when it was present (wrapped)
- [x] 2.5 `npm run lint`, `npm test`; `cd hub/ui && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`; commit `hub/ui/src` and `hub/hub/static/ui` together. Per DECISIONS `2026-09-14-ui`, the bundle is committed only if it needs nothing from Python newer than `:8000`'s process: 2.4's and 2.4a's broadcasts are additive, and the UI must work without them (it invalidates on its own mutation)

## 3. Drive

- [x] 3.1 (driven 2026-09-26 on :8043, real Haiku builder, Chromium; scripts/drive/d0926_coverage_bar*.py) Trial Hub `:8010`: one agent records evidence; open the document, open the bar, open the row, Accept. The row reads accepted, the bar's *awaiting* count drops, and a task waiting on that evidence shows its integration. Screenshot
