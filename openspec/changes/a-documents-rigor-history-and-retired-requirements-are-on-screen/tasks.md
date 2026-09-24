## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2: an independent re-derivation against `hub/hub/api/v1/spec.py` (`rigor_history`, `list_requirements`, `requirement_detail`, `set_document_rigor`), `hub/hub/spec_rigor.py` (`history_for`, `set_rigor`), `hub/hub/requirement_coverage.py` (`include_retired`, `_state`), `SpecPhaseBar.tsx`, `SpecDocumentPanel.tsx`, `api/spec.ts`. Check the preamble's scope call on F211's second route against bundle B5's `the-coverage-bar-takes-the-evidence-decision-it-asks-for` as it then stands
- [x] 0.2 R3: a second independent re-derivation (design round log). `openspec validate a-documents-rigor-history-and-retired-requirements-are-on-screen --strict` passes
- [ ] 0.3 The operator answers Open Question 1 (demotion requires a reason, recommended yes)
- [x] 0.3a Operator review fixes applied (`spec-queue/tracks/reviews/B6-2026-09-24.md` §4 LOW): the rigor mutation invalidates `specRigorHistory` on success (D4, test 1.10)

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 Control (backend, `hub/tests/`): with two rigor changes, `GET /documents/{path}/rigor-history` returns them oldest first; `GET /spec/requirements?document=` includes a retired row with `state: "retired"`; `GET /spec/requirements/FR-2?document=` for a retired requirement with a linked task returns the task. Find the existing tests that already pin these (`grep -rn "rigor-history\|spec/requirements" hub/tests`) and record them; add only what is missing. These are the payload orders the UI tests below must use

UI, extend `hub/ui/src/__tests__/specPhaseBar.test.tsx`; new `specRetiredRequirements.test.tsx` (mock `@/api/spec`):

- [ ] 1.2 (D1, F190) The history fixture is **in the route's order** (ascending: `sketch→contract` at t1, then `contract→gate` at t2). The rendered list shows `contract → gate` first. Reversing the fixture, or a component that did not reverse, fails this. The toggle reads `History (2)`; with zero events there is no toggle. FAILS today (no history)
- [ ] 1.3 (D2) Choosing `sketch` on a `gate` document does **not** call the mutation; it shows the confirm row with Confirm disabled; typing a reason enables it; Confirm calls the mutation with `{path, rigor: 'sketch', reason: <typed>, expectedDigest}`. FAILS today (the select posts immediately, with no reason)
- [ ] 1.4 (D2) Choosing `gate` on a `sketch` document shows the confirm row with Confirm **enabled** and an empty reason; Confirm calls the mutation with `reason: ''`. Cancel calls nothing and the select shows the original value
- [ ] 1.5 (D2) Control: a 409 with `blocking` still renders `spec-rigor-refusal` lines, now after Confirm
- [ ] 1.6 (D3) Requirements fixture in the route's order (`FR-1`, `FR-10`, `FR-2`, string-sorted as `list_requirements` returns them) with `FR-10` and `FR-2` retired: the collapsed line reads `2 retired requirements`; expanded, `FR-2` is listed before `FR-10` (the component's numeric sort, on purpose). An all-active fixture renders nothing
- [ ] 1.7 (D3) Expanding `FR-2` calls `useSpecRequirement('FR-2', path)`; with a detail fixture carrying one task and one evidence piece, both are shown, and clicking the task calls `onOpenTasks([taskId])`; the coverage line reads `retired`
- [ ] 1.8 (D5) A detail query in error state shows `Could not load` and the error body, not a skeleton
- [ ] 1.9 (D4) `useSpecEvents` invalidates the three new keys on `spec_updated`
- [ ] 1.10 (D4, review LOW) With a real `QueryClient` (mock only `postJson`/`getJson`), a successful `useSetSpecRigor` call for `path` invalidates `['project', <id>, 'specRigorHistory', path]` with no SSE event, so the history query refetches. FAILS today (the mutation invalidates only `specDocuments` and `specs`)

## 2. The fix

- [ ] 2.1 Hooks in `api/spec.ts`; `SpecPhaseBar.tsx` (history toggle, confirm row); `SpecRetiredRequirements.tsx`; mount after the coverage bar in `SpecDocumentPanel.tsx`
- [ ] 2.2 Run group 1; `npm run lint`, `npx vitest run`; record counts. `py -3.11 -m pytest hub/tests/ -q` only if 1.1 added backend tests
- [ ] 2.3 `npm run build`, `py -3.11 scripts/refresh_ui_bundle.py`; commit source and bundle together

## 3. Drive it

- [ ] 3.1 On a trial Hub from source (never `:8000`): raise a document to `gate` with no reason, then lower it to `sketch` — the app refuses to confirm until a reason is typed; the history shows both, newest first, the second with its reason. Save a revision that drops a requirement that a task links; the document shows `1 retired requirement`; expanding it shows the task. Screenshot each step
