## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2: an independent re-derivation against `hub/hub/api/v1/spec.py` (`reindex`, `arrange_document`, `adopt_corpus`, `adopt_document`), `hub/hub/spec_documents.py` (`build_index`, `_select_home`, `write_index`), `hub/hub/spec_adoption.py`, `hub/ui/src/api/spec.ts`, `SpecDocumentBrowser.tsx`, `SpecTree.tsx`, `SpecDocumentPanel.tsx`, `specNavigation.ts`. Decide design D6's flag (a reindex that fails mid-write): file it or not
- [x] 0.2 R3: a second independent re-derivation (design round log). `openspec validate the-corpus-is-indexed-arranged-and-adopted-from-the-app --strict` passes
- [ ] 0.3 The operator answers the merge decision (design, recommended M1); record in `spec-queue/DECISIONS.md`
- [x] 0.3a Operator review fixes applied (`spec-queue/tracks/reviews/B6-2026-09-24.md` §3): F434 carried — D6 rewritten, MODIFIED delta on `spec-document-authority`, tests 1.12–1.15, tasks 2.1a–2.1c

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 (D5) `hub/tests/test_spec_index_writer.py`: patch `hub.api.v1.spec.sse_manager.broadcast`; `POST /spec/reindex` broadcasts `spec_updated` once, after the index is written. FAILS today
- [ ] 1.12 (D6, F434) `test_spec_index_writer.py`: a corpus with a valid `spec/index.json` and a document whose requirements changed on disk. Monkeypatch `pathlib.Path.write_text` (and so any temporary file `write_index` uses) to raise `OSError(28, "No space left on device")` when the target is in `spec/` and its name starts with `index.json`. `POST /spec/reindex` → **200**, `index.written` is `null`, `index.diagnostics` ends with `code == "index_write_failed"` and `actual` containing `No space left on device`, and `corpus.rerendered == []`. A fresh session reads the new requirement rows, so they were committed. `spec/index.json` is byte-identical to before. FAILS today (the `OSError` escapes: a 500, and the requirement rows are rolled back)
- [ ] 1.13 (D6, F434) The same patch, raising only for one document's file (not the index). `POST /spec/reindex` (a rebuild that re-renders two documents) → 200. That document is in `corpus.skipped` with `reason == "write_failed"` and the OS message. The other is in `corpus.rerendered`, and its stored `content_digest` equals the digest of its new file (read in a fresh session). The failed document's digest is unchanged. FAILS today (500)
- [ ] 1.14 (D6, F434) `POST /spec/documents/arrange` with the index write patched to fail → **500** with `detail.code == "index_write_failed"` and a `detail.message` naming the reason (not the plain `Internal Server Error`). `spec/index.json` is byte-identical, and no document file changed (compare bytes before and after). FAILS today (the `OSError` is unhandled)
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
- [ ] 1.15 (D2, D6) UI, `specCorpusStrip.test.tsx`: rebuild answers `{index: {written: null, diagnostics: [{code: 'index_write_failed', path: 'spec/index.json', actual: 'No space left on device', …}]}}`. The strip shows the reason and that the requirements were rebuilt, offers **Rebuild index**, and does **not** show *Nothing to index* or the home question

## 2. The fix

- [ ] 2.1 (D5) `reindex` broadcasts after commit
- [ ] 2.1a (D6) `spec_documents.write_index` writes `spec/index.json.tmp` with `Path.write_text` and `os.replace`s it over the index (test 1.12's patch relies on `write_text`); on failure it removes the temporary file and re-raises
- [ ] 2.1b (D6) `reindex` catches `OSError` around `write_index`: `written: null`, the `index_write_failed` diagnostic, no re-render, still commits. `arrange` catches it before any re-render: 500 with `{message, code: "index_write_failed"}`
- [ ] 2.1c (D6) `rerender_corpus` catches `OSError` per document into `skipped` (`reason: "write_failed"`, `message`), advancing no digest and recording no event for it
- [ ] 2.2 Hooks in `api/spec.ts`; `SpecCorpusStrip.tsx`; the Adopt affordance in `SpecTree.tsx`; **Place under…** in `SpecDocumentPanel.tsx`
- [ ] 2.3 Run group 1; full `py -3.11 -m pytest hub/tests/ -q` count inline; `npm run lint`, `npx vitest run`, `ruff`, `black` clean
- [ ] 2.4 `npm run build`, `py -3.11 scripts/refresh_ui_bundle.py`; commit source and bundle together

## 3. Drive it

- [ ] 3.1 On a trial Hub from source (never `:8000`), a project whose `spec/` holds three documents written by hand (payload blocks) and no records, no `spec/index.json`. In the app: the browser says no usable index and 3 untracked; **Adopt all 3**; **Rebuild index** asks for a home; choose one; the index is written (read `spec/index.json`); open a second document and **Place under…** the home; its rendered page shows the home and parent links; try to place the home under that child → the cycle refusal is shown. Screenshot each step
