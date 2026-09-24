# Design — the corpus is indexed, arranged and adopted from the app

**Built on the recommended answer to the merge decision: merge stays out of this change** (option M1
below). If the operator answers M2 or M3, the merge surface is a separate change after this one; this
change is unchanged.

**Round 1, 2026-09-24.** Nothing here is implemented yet.

## Context

On `404c7d5`, the four routes this change reaches, and what each returns:

| Route | Success | Refusals | Broadcast |
|---|---|---|---|
| `POST /spec/reindex` (`spec.py:1213-1286`), body `{home?}` | 200 `{documents: {path: counts or null}, references, index: {written: {path, documents, home} or null, diagnostics}, corpus: {rerendered, skipped}}` | none as HTTP; a missing home is `written: null` with `index_home_required` plus `home_ambiguous` or `home_missing` in `diagnostics` (`spec_documents.py:326-337`, `:455-469`) | **none** |
| `POST /spec/documents/arrange` (`:1309-1387`), body `{path, parent?}` | 200 `{path, parent, corpus}` | 400 unsafe path; 409 no usable index (F208 wording, `:1338-1348`); 404 not in index; 422 `this placement is not allowed` + `load_manifest` diagnostics | `spec_updated {path, parent}` |
| `POST /documents/adopt` (`:1486-1524`), body `{path}` | 201 document view + adoption fields | 400/409/422 by `_ADOPTION_REFUSAL_STATUS` (`:1475-1483`), `detail: {message, path, code, differences}` | `spec_updated {path, phase}` |
| `POST /spec/adopt` (`:1390-1416`), no body | 200 `{documents: {path: {adopted, …}}, adopted, skipped, diagnostics}` — never fails as a whole | none | `spec_updated {path: null}` when anything was adopted |

The UI already knows the index state and the untracked documents: `GET /specs` returns `manifest:
{state, version}`, `home`, `missing`, `diagnostics` (`api/spec.ts:61-67`), and each `SpecEntry` has
`document_id: null` for a file discovery found and the Hub never recorded (`api/spec.ts:23-27`,
carried to `SpecNode.documentId`, `specNavigation.ts:28-32,145`). `SpecDocumentBrowser`
(`components/spec/SpecDocumentBrowser.tsx`) is the one browser both the Ctrl+K picker and the specs
index tab host (its docstring, `:52-57`).

### Why merge is out (the decision)

`POST /documents/{path}/merge` (`:1638-1714`) requires the operator to supply **the whole new payload
of a capability document** (`MergeRequest.payload`), citing finished changes. No screen can author a
payload, and no agent can write a capability document: `save_document` refuses any non-operator actor
(`spec_service.py:159-162`, code `capability_write_is_the_operators`), and there is no operator
authoring surface either (`PUT /documents/{path}/content`, `spec.py:470-532`, has no client). So a
capability document has no authoring path in the product at all, and a merge button would be a
button over a JSON editor.

| Option | What it means | Breaks | Releases |
|---|---|---|---|
| **M1. Leave merge API-only for now** (recommended) | F206 closes for four routes; merge is recorded as waiting on capability authoring. | Nothing. | This change stays small and shippable. |
| M2. A merge dialog with a payload editor | The operator hand-edits JSON. | The product's premise that agents author and the operator judges. | A surface that no operator would use. |
| M3. Agents draft capability content as proposals | An agent submits a capability payload; it always lands as proposals (whatever the rigor); accepting them records the merge as the operator's. | Changes `spec-document-authority`'s *capability documents are written by the operator* into *accepted by the operator*. | A real authoring path — and a spec-flow design question bigger than this bundle. |

Recommended M1 now, with M3 as the likely eventual answer, taken as its own exploration.

## Decisions

### D1 — One corpus strip in the browser

`SpecCorpusStrip`, rendered at the top of `SpecDocumentBrowser` above the results, from the
`useSpecList` query both hosts already make. Content:

- **Index:** `valid` → *"Index: home is <title>"* and a quiet **Rebuild index**; `absent` /
  `unreadable` / `invalid` → *"No usable index — hierarchy and home are not recorded"* and
  **Rebuild index** as the primary action.
- **Untracked:** when N > 0 entries have `document_id == null` (and are not `missing`) →
  *"N documents on disk are not tracked"* and **Adopt all N**.

Nothing renders when the index is valid and nothing is untracked, except the quiet Rebuild.

### D2 — Rebuild asks for a home only when the Hub asks

**Rebuild index** posts `reindex` with no body. If the answer has `index.written == null` and its
`diagnostics` carry `index_home_required`, the strip turns into a question: *"Which document is the
corpus's home?"* — a select of the documents that are **both tracked and on disk** (`useSpecList`
entries with a `document_id`), preselecting none — and **Rebuild with this home** posts `{home}`.
R2 corrected R1's source (`useSpecDocuments`): `build_index` files only documents that are on disk
*and* known (`spec_documents.py:259-269`), so a tracked row whose file is gone would answer
`home_missing` plus `index_home_required` again and loop the question. When `written == null` and
there is no home diagnostic (no tracked document is on disk, `:318-319`), the strip says *"Nothing
to index: no tracked document is on disk"* and points at Adopt. Otherwise it shows the summary: documents indexed
(`written.documents`), totals of `created` / `reworded` / `retired` across `documents`,
`corpus.rerendered.length` re-rendered, and each `corpus.skipped` entry with its reason. Every
diagnostic in `index.diagnostics` other than the home ones is listed verbatim (`code — path`);
`unindexable_document` (a file with no row, `:271-275`) is listed with an **Adopt** action beside it.

The choice is never made for the operator: `_select_home`'s refusal to guess (`spec_documents.py:
440-455`) is the behaviour this dialog serves, not one it works around.

### D3 — Adopt, one or all, with the Hub's own reasons

A row in `SpecTree` whose node has `documentId == null` and `missing == false` shows an **Adopt**
button (rail and dialog density alike). It posts `documents/adopt {path}`. A refusal shows its
`detail.message`, and for `document_exists` its `differences` (`field: file vs row`).

**Adoption does not file a document in the index** (R2: nothing in `spec_adoption.py` writes
`spec/index.json`; `write_index` has two callers, reindex and arrange). So after any successful
adopt the strip shows **Rebuild index** as its primary action with *"Adopted documents are filed
in the index on the next rebuild"*; without it an adopted document cannot be placed (arrange answers
404 *not in the index*).

**Adopt all N** posts `spec/adopt`, then lists `skipped` paths with each `documents[path].message`,
and `diagnostics` verbatim — `discovery_truncated` in particular, because *"a truncated sweep
presented as a complete one is the worst outcome this operation has"* (`spec_adoption.py:360-362`).

### D4 — Place under… lives on the document

In `SpecDocumentPanel`'s header, beside the breadcrumb, **Place under…** opens a select of every
document in the index (`useSpecList().specs` with `state == 'filed'`), minus the document itself, plus
*No parent*, preselecting the current `parent`. It posts `arrange {path, parent}`. On 409 it shows
the message and a **Rebuild index** button that runs D2's flow; on 422 it lists `diagnostics`; on
404 (*not in the index*) it says the document is not filed yet and offers Rebuild. Hidden for a
document that is not filed and when there is no valid index (the 409 path is still reachable if the
list is stale).

### D5 — reindex broadcasts

`reindex` broadcasts `spec_updated {"path": null}` after commit. The UI's mutation hooks invalidate
`specs`, `specDocuments` (the shared `useSpecMutation` already does, `api/spec.ts:244-256`) and the
open document's content (`['project', pid, 'spec']`, prefix), because arrange and reindex re-render
files.

### D6 — What each route answers when what it calls raises

- `reindex`: `spec_documents.write_index` and `rerender_corpus`'s file writes can raise `OSError`
  (disk, permissions). That is an unhandled **500 after files may already be written** and before
  the database commit — `spec/index.json` or a re-rendered document can be on disk while the
  digests recorded for them are rolled back. This change does not alter it (a pre-existing
  ordering, shared by `arrange`, `spec.py:1375-1379`); the strip shows the 500 body and says
  *"the index may be partly written — rebuild again"*. **R2 confirmed it from the code**:
  `write_index` is a plain `write_text` (`spec_documents.py:345`), `rerender_corpus` calls
  `write_document` unwrapped (`spec_service.py:881`), and both routes commit only afterwards
  (`spec.py:1265`, `:1379`). Not carried: the orchestrator decides whether to file it (see the
  bundle record's candidates).
- `arrange`, `adopt`, `spec/adopt`: every refusal is before any write. `spec/adopt` never fails as a
  whole by design.

## Goals / Non-Goals

**Goals:** every corpus-shaping route an operator is meant to use is on a screen; the home question
is answered where it is asked.

**Non-Goals:** merge (decision above); drag-and-drop arrangement; showing the parent hierarchy in
`SpecTree` (it is built from paths, `buildPathTree`, and the hierarchy shows in the rendered
documents' own navigation — a separate question).

## Risks / Trade-offs

- **Adopt beside every untracked row** adds a control to a tree used mostly for reading. It shows
  only on untracked rows, which a healthy corpus does not have.
- **Rebuild re-renders documents.** `rerender_corpus` is bounded to documents whose bytes change
  (`spec-corpus-map`, *"Regeneration is bounded to the documents the arrangement changed"*), and its
  own regeneration is not reported as drift (*"A regenerated document is not reported as drifted"*).

## Open Questions

1. **Merge: M1, M2 or M3?** Recommended M1 now; M3 as its own exploration.

## Round log

### Round 2 — 2026-09-24 (B6 R2)

Re-derived the four routes' bodies and refusals (`spec.py:1213-1416`, `:1470-1524`), `build_index`
and `_select_home` (`spec_documents.py:247-469`), `rerender_corpus`, and the UI types
(`api/spec.ts:15-67`, `specNavigation.ts:27-32`). Corrected: the home select's source (D2); the
empty-corpus answer (D2); adoption leaves the document unindexed (D3). D6's ordering hazard
confirmed. F205 (`SpecPhaseBar.tsx:146-160`) and F208 (`spec.py:1338-1348`) confirmed fixed, both
marked fixed in the ledger.

### Round 1 — 2026-09-24 (B6 R1)

F206 re-verified by grep over `hub/ui/src` (no caller of any of the five) and by reading each route.
F205 and F208 confirmed fixed by reading `SpecPhaseBar.tsx:146-160` and `spec.py:1338-1348` and by
`git log -S` (`58477dc`, `568f868`).
