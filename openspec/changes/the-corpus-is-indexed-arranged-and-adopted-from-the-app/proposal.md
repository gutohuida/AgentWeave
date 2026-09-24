# Proposal — the corpus is indexed, arranged and adopted from the app

**Round 1, 2026-09-24** (bundle B6, slice S5c). Finding: **F206 (B)**, four of its five routes.
The fifth, `POST /documents/{path}/merge`, is **not carried**: it needs an authored payload for a
capability document, and nothing in the product can author one (design, "Why merge is out"); it is
put to the operator as a decision. The slice's other two findings are already fixed:
**F205** (`58477dc`, UI-1 — the phase bar offers Archive on `exploring` and `proposed`,
`SpecPhaseBar.tsx:146-160`) and **F208** (`568f868`, Round 4b — the arrange refusal names the reindex
and the home, `spec.py:1338-1348`). By the operator's review of 2026-09-24
(`spec-queue/tracks/reviews/B6-2026-09-24.md` §3) it also carries **F434 (B)**: reindex and arrange
write files before the database commit, so a disk error answers a bare 500 with files written and
the requirement index rolled back. **Nothing here is implemented yet.**

## Why

The corpus-shaping half of the spec flow works and is reachable only by `curl`. Re-verified on
`404c7d5`: `grep -rn "spec/reindex\|documents/arrange\|spec/adopt\|documents/adopt" hub/ui/src` →
nothing; `agent_actions.py` has none of them, by design (each is operator-only).

- `POST /spec/reindex` is the only writer of `spec/index.json` — *"the only record of the corpus's
  home, hierarchy and ordering that survives the project being copied to another machine"*
  (`spec.py:1227-1229`). When no home is recorded and more than one document exists it writes
  nothing and asks for one (`spec_documents.py:333-337`, `:469`) — a question no screen can answer.
- `POST /spec/documents/arrange` sets a document's parent — design D3's *"editorial judgement about
  what the project is"* (`spec.py:1297-1303`). Without it a document's rendered navigation and its
  parent's child map can never reflect a hierarchy.
- `POST /documents/adopt` and `POST /spec/adopt` recover a corpus whose files predate its database
  rows — a clone, a restore, a second machine (`spec-document-adoption`, *"A corpus is adoptable in
  one operation"*). The document browser already shows such files (a `SpecEntry` with `document_id:
  null`, `specNavigation.ts:28-32`) and offers nothing to do with them.

## What Changes

- **Index state and a Rebuild action in the document browser** (`SpecDocumentBrowser`, which both the
  Ctrl+K picker and the specs index tab host): a one-line strip naming the index's state from
  `GET /specs` (`manifest.state`, `home`), and **Rebuild index**. When the rebuild answers that a home
  is needed (`index_home_required`, `home_ambiguous`, `home_missing`), the strip asks which document
  is home and rebuilds with it. The result is summarised (documents indexed, requirements created,
  reworded, retired; documents re-rendered and skipped).
- **Adopt from the browser**: an untracked document row offers **Adopt**; when there are any, the
  strip offers **Adopt all N**. Each refusal or skip is shown with the Hub's own reason.
- **Place a document under another from the document**: a **Place under…** control in the
  `SpecDocumentPanel` header, listing the index's documents and *No parent*. A 409 (no usable index)
  shows **Rebuild index** in place; a 422 (cycle, self, unknown) shows the diagnostics.
- **A file that cannot be written is reported, not a bare 500 (F434).** If `spec/index.json` cannot
  be written, `reindex` answers 200 with `written: null` and an `index_write_failed` diagnostic
  naming the reason, and still commits the requirement index. A document that cannot be re-rendered
  is listed in `skipped` and the rest carry on. `arrange` refuses with a sentence. The index is
  replaced atomically, so a failed write leaves the previous one. This is a MODIFIED delta on
  `spec-document-authority`'s *"A failure to write the index does not abandon the requirement
  index"*, whose SHALL the bare 500 already breaks.
- **`reindex` announces itself**: it broadcasts `spec_updated` after commit, as `arrange`,
  `adopt` and `spec/adopt` already do (`spec.py:1381`, `:1519-1523`, `:1415`). Today it does not, so a
  second window keeps the old tree.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `spec-corpus-map` — adds *"The operator shapes the corpus from the app"*.
- `spec-document-adoption` — adds *"An untracked document is adoptable from where it is listed"*.
- `spec-document-authority` — modifies *"A failure to write the index does not abandon the
  requirement index"* (an OS write failure, a re-render failure, and a placement whose index cannot
  be written).

## Impact

- `hub/hub/api/v1/spec.py` — `reindex` broadcast; `reindex` and `arrange` catch the index write's
  `OSError` (F434).
- `hub/hub/spec_documents.py` — `write_index` replaces the file atomically.
- `hub/hub/spec_service.py` — `rerender_corpus` reports a document it could not write as skipped.
- `hub/ui/src/api/spec.ts` — `useReindexSpec`, `useArrangeSpecDocument`, `useAdoptSpecDocument`,
  `useAdoptSpecCorpus`.
- `hub/ui/src/components/spec/SpecCorpusStrip.tsx` (new), mounted in `SpecDocumentBrowser.tsx`;
  `SpecTree.tsx` (an Adopt affordance on untracked rows); `SpecDocumentPanel.tsx` (Place under…).
- UI bundle refresh.

Decision for the operator (not carried): **who authors a capability document, and so who can call
merge** — see design.
