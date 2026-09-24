## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2: an independent re-derivation against `hub/hub/api/v1/spec.py` (`detect_drift`, `list_drift`, `resolve_drift`), `hub/hub/requirement_evidence.py` (`detect_drift`, `resolve_drift`, `open_drift_for`), `hub/hub/requirement_gate.py`, `hub/ui/src/api/spec.ts`, `SpecDocumentPanel.tsx`, `SpecCoverageBar.tsx`. Check in particular that `spec_updated` with `path: null` is safe for every consumer of that event (`grep -rn spec_updated hub/ui/src`)
- [x] 0.2 R3: a second independent re-derivation (design round log). `openspec validate drift-is-scanned-and-answered-on-the-document --strict` passes
- [ ] 0.3 `drift-watches-the-files-its-evidence-is-about` is implemented and archived (or at least merged) first. The operator confirms the manual scan (design preamble) and Open Question 1

## 1. Tests first — each must fail on today's code unless marked as a control

Backend in `hub/tests/test_requirement_drift.py` (its fixtures; evidence recorded with a locator, as the first change requires).

- [ ] 1.1 (D1) Two documents, a candidate on each; `GET /spec/drift?document=<first>&state=candidate` returns only the first's. FAILS today (filters ignored: both returned)
- [ ] 1.2 (D1) A resolved and an open candidate on one document; `state=candidate` returns only the open one; `state=bogus` → 422; an unknown `document` → 404. FAILS today
- [ ] 1.3 (D4) Resolve a candidate, then resolve it again with a different resolution → 409, `detail.code == "drift_not_open"`, message names the first resolution; `GET /spec/drift` still shows the first resolution. FAILS today (200, overwritten)
- [ ] 1.4 (D5) Patch `hub.api.v1.spec.sse_manager.broadcast`; `detect` with nothing to raise still broadcasts `spec_updated` with `drift: True`; `resolve` broadcasts once. FAILS today (no broadcast)
- [ ] 1.5 (D6) A `gate`-rigor document whose requirement is drifting; approval of a task linking it is refused and the message contains `the operator answers the drift candidate` and `an agent cannot`. FAILS today. Build it on the staging `test_requirement_coverage.py::test_drifting_outranks_verified` uses
- [ ] 1.6 Control: `test_drifting_outranks_verified` and the rest of `test_requirement_coverage.py` pass before and after

UI in a new `hub/ui/src/__tests__/specDriftPanel.test.tsx` (mock `@/api/spec` as `specProposalsPanel.test.tsx` does).

- [ ] 1.7 (D1, F190) The fixture is **in the route's order** — two candidates, `created_at` ascending, the older naming `FR-1`. The rendered rows are `FR-1` then `FR-2`. A component that sorted newest-first, or a fixture reversed, fails this. Each row shows the moved path and `was → now` as 7-character ids, and the evidence summary
- [ ] 1.8 (D1) Each of the three buttons calls the resolve mutation with its enum value and the candidate id; a rejected mutation shows the refusal's `detail.message` on the row
- [ ] 1.9 (D2) **Scan for drift** calls the detect mutation; with `raised` of two ids, one of which is in the refetched list, the sentence reads `2 new — 1 on this document`
- [ ] 1.10 (D3) An `unwatched` entry with `reason: "names_no_file"` renders the count line and, expanded, the remedy sentence
- [ ] 1.11 (D1) With no candidates, no unwatched entries and coverage totals of zero verified/drifting/stale, the panel renders nothing
- [ ] 1.12 (D5) `useSpecEvents` invalidates `['project', <id>, 'specDrift']` on `spec_updated` (extend the existing test of that hook, or add one)

## 2. The fix

- [ ] 2.1 (D4) `resolve_drift` state check; route maps `exc.http_status or 422`
- [ ] 2.2 (D1, D3, D7) `list_drift(document, state)`; `unwatched` takes the same `document` filter
- [ ] 2.3 (D5) Broadcasts in `detect` and `resolve`, after commit
- [ ] 2.4 (D6) `REMEDY[DRIFTING]`
- [ ] 2.5 UI: hooks in `api/spec.ts`; `SpecDriftPanel.tsx`; mount in `SpecDocumentPanel.tsx` after `SpecCoverageBar`; change `SpecCoverageBar`'s *Drifting* `why` to end `…which one was wrong — answer it under Drifting, below.`
- [ ] 2.6 Run group 1; `py -3.11 -m pytest hub/tests/ -q` full count inline; `cd hub/ui && npm run lint && npx vitest run`; `ruff`, `black` clean
- [ ] 2.7 `cd hub/ui && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`; commit `hub/ui/src` and `hub/hub/static/ui` together

## 3. Drive it

- [ ] 3.1 On a trial Hub from source (never `:8000`): a git fixture, a `gate` document, operator evidence naming a file; commit a change to that file; open the document in the app; press **Scan for drift**; the strip shows the candidate; the coverage bar reads *Drifting*; approving a linked task is refused with the new remedy; revert the file and commit, then press **Code corrected** (R3: the answer silences that change whatever it says, so the drive must make it true); the strip empties and the bar reads *Verified* in a second open tab without reload. Screenshot each step
