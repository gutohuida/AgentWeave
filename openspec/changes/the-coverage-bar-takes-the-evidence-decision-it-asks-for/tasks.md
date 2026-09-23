## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1: explore and propose (2026-09-24, bundle B5)
- [ ] 0.2 R2: independent re-derivation against `SpecCoverageBar.tsx`, `SpecDocumentPanel.tsx`, `api/spec.ts` (`useSpecEvents`), `api/tasks.ts` (every task-scoped query key), `spec.py` list/decision routes, `agent_actions.py` decision route, `sse.py`. Confirm the list route's order; confirm neither decision route broadcasts today; answer design Open Question 2
- [ ] 0.3 R3: second independent re-derivation; `openspec validate the-coverage-bar-takes-the-evidence-decision-it-asks-for --strict` passes
- [ ] 0.4 The operator approves (APPROVALS.md)

## 1. Tests first — each fails on today's code unless marked as a control

- [ ] 1.1 (D3, backend) `hub/tests/test_evidence_decision_is_announced.py`: subscribe to the project's SSE queue (the pattern in the existing `spec_updated` tests — R2 names one), decide a piece through `POST /spec/evidence/{id}/decision`, assert one `spec_updated` event carrying the evidence id. The same through the agent plane with a granted agent. FAILS today (no event)
- [ ] 1.2 (D1, UI) `hub/ui/src/__tests__/evidencePieces.test.tsx`: mock `GET /spec/evidence?identifier=FR-1&document=…` returning **two awaiting pieces oldest first** (the route's order). Assert both render with summary, actor, `commit_sha[:12]` and branch, and that the *newest* label is on the **second**. Reversing the fixture must fail the label assertion. FAILS today (component absent)
- [ ] 1.3 (D1) Accept posts `{"decision":"accepted","reason":""}` to `/spec/evidence/<id>/decision` for the clicked piece
- [ ] 1.4 (D1) Reject is disabled with an empty reason; with a reason it posts `{"decision":"rejected","reason":…}`
- [ ] 1.5 (D2) A 403/409 response renders the detail message beside the piece; the piece still shows Accept
- [ ] 1.6 (D2) A row with `recording_run_live: true` renders disabled buttons and the *still being recorded* sentence
- [ ] 1.7 (D1) `specCoverage.test.tsx`: a row with `evidence_count: 0` has no Evidence toggle; with `evidence_count: 2`, it has one. Existing assertions in that file keep passing (control)
- [ ] 1.8 (D3) The mutation's success invalidates `specCoverage` and the task keys R2 lists (spy on `queryClient.invalidateQueries`)

## 2. The fix

- [ ] 2.1 `api/spec.ts`: `EvidencePiece` type (the `_evidence_view` shape plus optional `recording_run_live`), `useSpecEvidence(path, identifier, enabled)` keyed `['project', pid, 'specEvidence', path, identifier]`, `useDecideEvidence()`; `useSpecEvents` also invalidates `specEvidence`
- [ ] 2.2 `components/spec/EvidencePieces.tsx` per design D1/D2
- [ ] 2.3 `SpecCoverageBar.tsx`: an *Evidence (n)* toggle on rows with `evidence_count > 0`, mounting `EvidencePieces`
- [ ] 2.4 `spec.py` and `agent_actions.py` decision routes: broadcast `spec_updated` after integration
- [ ] 2.5 `npm run lint`, `npm test`; `cd hub/ui && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`; commit `hub/ui/src` and `hub/hub/static/ui` together. Per DECISIONS `2026-09-14-ui`, the bundle is committed only if it needs nothing from Python newer than `:8000`'s process: 2.4's broadcast is additive, and the UI must work without it (it invalidates on its own mutation)

## 3. Drive

- [ ] 3.1 Trial Hub `:8010`: one agent records evidence; open the document, open the bar, open the row, Accept. The row reads accepted, the bar's *awaiting* count drops, and a task waiting on that evidence shows its integration. Screenshot
