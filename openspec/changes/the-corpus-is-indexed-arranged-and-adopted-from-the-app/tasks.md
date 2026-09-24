## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2: an independent re-derivation against `hub/hub/api/v1/spec.py` (`reindex`, `arrange_document`, `adopt_corpus`, `adopt_document`), `hub/hub/spec_documents.py` (`build_index`, `_select_home`, `write_index`), `hub/hub/spec_adoption.py`, `hub/ui/src/api/spec.ts`, `SpecDocumentBrowser.tsx`, `SpecTree.tsx`, `SpecDocumentPanel.tsx`, `specNavigation.ts`. Decide design D6's flag (a reindex that fails mid-write): file it or not
- [x] 0.2 R3: a second independent re-derivation (design round log). `openspec validate the-corpus-is-indexed-arranged-and-adopted-from-the-app --strict` passes
- [ ] 0.3 The operator answers the merge decision (design, recommended M1); record in `spec-queue/DECISIONS.md`

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 (D5) `hub/tests/test_spec_index_writer.py`: patch `hub.api.v1.spec.sse_manager.broadcast`; `POST /spec/reindex` broadcasts `spec_updated` once, after the index is written. FAILS today
- [ ] 1.2 Control: the rest of `test_spec_index_writer.py`, `test_spec_adoption_api.py`, `test_spec_adoption_corpus.py` and `test_a_refusal_says_what_would_work.py` pass before and after; record counts

UI, new `hub/ui/src/__tests__/specCorpusStrip.test.tsx` and additions to the browser/tree/panel tests (mock `@/api/spec`):

- [ ] 1.3 (D1) `manifest.state: 'absent'` → the strip says no usable index and shows **Rebuild index**; `'valid'` with `home` → names the home's title
- [ ] 1.4 (D2) Rebuild answers `{index: {written: null, diagnostics: [{code: 'home_ambiguous', …}, {code: 'index_home_required', …}]}}` (the order `build_index` appends them: the home diagnostic first, then `index_home_required`, `spec_documents.py:330-337`) → the home question appears; choosing a document and confirming calls the mutation with `{home: <path>}`. A fixture that only carried `index_home_required` must still trigger it (the component keys on that code, not on position)
- [ ] 1.5 (D2) Rebuild answers a written index → the summary shows `written.documents`, the `created/reworded/retired` totals, and each `corpus.skipped` entry
- [ ] 1.6 (D3) An untracked, not-missing node in `SpecTree` shows **Adopt**; a tracked node does not; a missing node does not. Pressing it calls the adopt mutation with the path; a 409 `document_exists` refusal shows the message and one `differences` row
- [ ] 1.7 (D3) **Adopt all 2** → the corpus adopt mutation; a result with one `skipped` path shows its `documents[path].message`, and a `discovery_truncated` diagnostic is shown
- [ ] 1.8 (D4) **Place under…** lists filed documents minus the open one plus *No parent*, preselects the current parent, and calls arrange with `{path, parent}`; *No parent* sends `parent: null`
- [ ] 1.9 (D4) A 409 from arrange shows the message and a **Rebuild index** button; a 422 lists its diagnostics
- [ ] 1.10 (D2, R2) The home select lists only `useSpecList` entries with a `document_id` (a tracked document whose file is gone is not offered); a rebuild answering `written: null` with no home diagnostic shows *Nothing to index*
- [ ] 1.11 (D3, R2) After a successful **Adopt**, the strip shows **Rebuild index** as its primary action with the sentence that adopted documents are filed on the next rebuild

## 2. The fix

- [ ] 2.1 (D5) `reindex` broadcasts after commit
- [ ] 2.2 Hooks in `api/spec.ts`; `SpecCorpusStrip.tsx`; the Adopt affordance in `SpecTree.tsx`; **Place under…** in `SpecDocumentPanel.tsx`
- [ ] 2.3 Run group 1; full `py -3.11 -m pytest hub/tests/ -q` count inline; `npm run lint`, `npx vitest run`, `ruff`, `black` clean
- [ ] 2.4 `npm run build`, `py -3.11 scripts/refresh_ui_bundle.py`; commit source and bundle together

## 3. Drive it

- [ ] 3.1 On a trial Hub from source (never `:8000`), a project whose `spec/` holds three documents written by hand (payload blocks) and no records, no `spec/index.json`. In the app: the browser says no usable index and 3 untracked; **Adopt all 3**; **Rebuild index** asks for a home; choose one; the index is written (read `spec/index.json`); open a second document and **Place under…** the home; its rendered page shows the home and parent links; try to place the home under that child → the cycle refusal is shown. Screenshot each step
