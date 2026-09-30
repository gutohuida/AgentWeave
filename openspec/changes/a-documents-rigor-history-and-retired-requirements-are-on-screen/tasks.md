## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2: an independent re-derivation against `hub/hub/api/v1/spec.py` (`rigor_history`, `list_requirements`, `requirement_detail`, `set_document_rigor`), `hub/hub/spec_rigor.py` (`history_for`, `set_rigor`), `hub/hub/requirement_coverage.py` (`include_retired`, `_state`), `SpecPhaseBar.tsx`, `SpecDocumentPanel.tsx`, `api/spec.ts`. Check the preamble's scope call on F211's second route against bundle B5's `the-coverage-bar-takes-the-evidence-decision-it-asks-for` as it then stands
- [x] 0.2 R3: a second independent re-derivation (design round log). `openspec validate a-documents-rigor-history-and-retired-requirements-are-on-screen --strict` passes
- [x] 0.3 The operator answers Open Question 1 (demotion requires a reason, recommended yes)
  Answered yes, APPROVALS 2026-09-24: *"Lowering rigor needs a reason; the history refreshes on success."*
- [x] 0.3a Operator review fixes applied (`spec-queue/tracks/reviews/B6-2026-09-24.md` §4 LOW): the rigor mutation invalidates `specRigorHistory` on success (D4, test 1.10)

## 1. Tests first — each must fail on today's code unless marked as a control

- [x] 1.1 Control (backend, `hub/tests/`): with two rigor changes, `GET /documents/{path}/rigor-history` returns them oldest first; `GET /spec/requirements?document=` includes a retired row with `state: "retired"`; `GET /spec/requirements/FR-2?document=` for a retired requirement with a linked task returns the task. Find the existing tests that already pin these (`grep -rn "rigor-history\|spec/requirements" hub/tests`) and record them; add only what is missing. These are the payload orders the UI tests below must use
  2026-09-30: already pinned — `test_every_rigor_change_is_recorded_and_attributed` (`test_requirement_gate.py`; the order, but read from the table, not the route), `test_a_retired_requirement_nobody_serves_is_retired_not_unserved` (`test_requirement_coverage.py`; detail of a retired `FR-2`, no task). Missing, added: `test_the_rigor_history_route_answers_oldest_first` (route, `sketch→contract` then `contract→gate`), `test_the_requirement_list_includes_retired_rows_in_string_order` (ten requirements, `FR-2`/`FR-10` retired: `FR-1, FR-10, FR-2`, states `retired`), `test_a_retired_requirement_still_answers_with_the_task_linked_to_it`. Controls: passed on first run (`test_requirement_gate.py` + `test_requirement_coverage.py`, 51 passed).

UI, extend `hub/ui/src/__tests__/specPhaseBar.test.tsx`; new `specRetiredRequirements.test.tsx` (mock `@/api/spec`):

- [x] 1.2 (D1, F190) The history fixture is **in the route's order** (ascending: `sketch→contract` at t1, then `contract→gate` at t2). The rendered list shows `contract → gate` first. Reversing the fixture, or a component that did not reverse, fails this. The toggle reads `History (2)`; with zero events there is no toggle. FAILS today (no history)
  2026-09-30: red before — no `spec-rigor-history-toggle`; green after. A component that did not reverse fails on `items[0]` (`sketch → contract`).
- [x] 1.3 (D2) Choosing `sketch` on a `gate` document does **not** call the mutation; it shows the confirm row with Confirm disabled; typing a reason enables it; Confirm calls the mutation with `{path, rigor: 'sketch', reason: <typed>, expectedDigest}`. FAILS today (the select posts immediately, with no reason)
  2026-09-30: red before — the mutation was called on the select's change; green after (whitespace-only reason also keeps Confirm disabled).
- [x] 1.4 (D2) Choosing `gate` on a `sketch` document shows the confirm row with Confirm **enabled** and an empty reason; Confirm calls the mutation with `reason: ''`. Cancel calls nothing and the select shows the original value
  2026-09-30: red before — the mutation was called on change / no `spec-rigor-confirm` for the Cancel case; green after.
- [x] 1.5 (D2) Control: a 409 with `blocking` still renders `spec-rigor-refusal` lines, now after Confirm
  2026-09-30: red before only because there was no Confirm to press (`spec-rigor-confirm` absent); the refusal parsing is unchanged, green after. `specRigor.test.tsx`'s three posting tests were updated to press Confirm and now also assert `reason: ''` on a promotion.
- [x] 1.6 (D3) Requirements fixture in the route's order (`FR-1`, `FR-10`, `FR-2`, string-sorted as `list_requirements` returns them) with `FR-10` and `FR-2` retired: the collapsed line reads `2 retired requirements`; expanded, `FR-2` is listed before `FR-10` (the component's numeric sort, on purpose). An all-active fixture renders nothing
  2026-09-30: red before — `SpecRetiredRequirements` did not exist (import failed; then, against a `null` stub, no `spec-retired-toggle`); green after. A component keeping the route's string order lists `FR-10` first and fails.
- [x] 1.7 (D3) Expanding `FR-2` calls `useSpecRequirement('FR-2', path)`; with a detail fixture carrying one task and one evidence piece, both are shown, and clicking the task calls `onOpenTasks([taskId])`; the coverage line reads `retired`
  2026-09-30: red before (no toggle, against the stub); green after. Two evidence pieces in route order (oldest first) are shown in that order.
- [x] 1.8 (D5) A detail query in error state shows `Could not load` and the error body, not a skeleton
  2026-09-30: red before (no toggle); green after. A list-level read failure also says `Could not load` with the body (`spec-retired-error`).
- [x] 1.9 (D4) `useSpecEvents` invalidates the three new keys on `spec_updated`
  2026-09-30: red before — invalidated keys lacked `specRigorHistory`; green after (all three prefixes).
- [x] 1.10 (D4, review LOW) With a real `QueryClient` (mock only `postJson`/`getJson`), a successful `useSetSpecRigor` call for `path` invalidates `['project', <id>, 'specRigorHistory', path]` with no SSE event, so the history query refetches. FAILS today (the mutation invalidates only `specDocuments` and `specs`)
  2026-09-30: red before — history `getJson` called 1 time, expected 2 (no refetch without SSE); green after (`useSetSpecRigor` now has its own `useMutation` + `onSuccess`, as `useSetSpecPhase` does; `useSpecMutation` unchanged).

## 2. The fix

- [x] 2.1 Hooks in `api/spec.ts`; `SpecPhaseBar.tsx` (history toggle, confirm row); `SpecRetiredRequirements.tsx`; mount after the coverage bar in `SpecDocumentPanel.tsx`
  2026-09-30: `api/spec.ts` (`useSpecRigorHistory`, `useSpecRequirements`, `useSpecRequirement`, `useSetSpecRigor` own `onSuccess`, `useSpecEvents` +3 keys, `CoverageEntry.state` gains `retired`); `SpecPhaseBar.tsx` (History toggle, inline confirm row); new `SpecRetiredRequirements.tsx`; mounted after `SpecCoverageBar` in `SpecDocumentPanel.tsx`. `specNavigationUi.test.tsx`'s `@/api/client` mock gained `readableApiError` (its reads all fail, and the new list says so).
- [x] 2.2 Run group 1; `npm run lint`, `npx vitest run`; record counts. `py -3.11 -m pytest hub/tests/ -q` only if 1.1 added backend tests
  **Result, 2026-09-30:** `py -3.11 -m pytest hub/tests/ -q` as CI's hub-test at `2f120b4` (run 36748774080, no `claude` on PATH): 5513 passed, 20 skipped, 0 failed, 16:04; that commit carries the ceiling fix below. UI: `npm run lint` clean; `npx tsc --noEmit -p .` clean; `npx vitest run` 172 files / 1785 tests passed. History: the first local full run (1.1 added backend tests) went red in four `test_surface_ceilings.py` tests, the n11 query-error ratchet (98 > 97), because `SpecPhaseBar`'s new `useSpecRigorHistory` call ignored its error. Fixed by saying *"Could not load the rigor history: …"* (`spec-rigor-history-error`; test *says the history could not be loaded when its read fails*, red with the line disabled, green with it); `test_surface_ceilings.py` then 6 passed. The local clean re-run was stopped by Claude Code for low system memory, so the task was unticked (`6ed8c28`) until CI's count above.
- [x] 2.3 `npm run build`, `py -3.11 scripts/refresh_ui_bundle.py`; commit source and bundle together
  2026-09-30: `npm run build` ok; `py -3.11 scripts/refresh_ui_bundle.py` refreshed `hub/hub/static/ui` and the stamp. Commit left to the operator's session.

## 3. Drive it

- [ ] 3.1 On a trial Hub from source (never `:8000`): raise a document to `gate` with no reason, then lower it to `sketch` — the app refuses to confirm until a reason is typed; the history shows both, newest first, the second with its reason. Save a revision that drops a requirement that a task links; the document shows `1 retired requirement`; expanding it shows the task. Screenshot each step
