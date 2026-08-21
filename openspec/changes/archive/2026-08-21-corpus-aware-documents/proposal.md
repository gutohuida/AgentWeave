## Why

The specification home document is thin, and the corpus has no navigation. The operator's words:
*"I was finding it thin. I expect to have a overview of the entire project there and the path to all
other features and specs."*

Arriving at the Spec tab with nothing open resolves the manifest home and opens it
(`hub/ui/src/components/spec/SpecPage.tsx:41-50`) — `spec/agentweave.html`, a `system-map` document.
So the landing page already exists and is already a document. What it does not contain is the map.

Two facts make that gap larger than it looks.

**The renderer knows nothing about the corpus.** `render_document`
(`hub/hub/spec_render.py:328-335`) takes a payload, identifiers, phase and rigor, and emits a
complete self-contained file. It has no home, no parent, no siblings, no notion that other documents
exist. Every one of the 35 documents on disk therefore renders as an island: opening
`spec/capabilities/agent-charter/spec.html` gives a reader no way back and no way across.

**The hierarchy field exists, is validated, and has no producer.** `spec/index.json` carries `path`,
`title`, `kind`, `status`, **`parent`** and `order` for all 33 filed documents. `parent` is checked
for unknown targets, self-reference and cycles (`hub/hub/spec_manifest.py:236-274`), and
`build_index` deliberately preserves it across rebuilds because *"`parent` and `order` are the
operator's arrangement, they have no column to live in, and a rebuild that recomputed them would
silently discard the only copy"* (`hub/hub/spec_documents.py:261-263`). It survives to the UI type
(`hub/ui/src/api/spec.ts:17,58`). And **nothing anywhere ever sets it** — all 33 entries read
`parent: null`, and `SpecTree` draws hierarchy from path prefixes instead
(`hub/ui/src/components/spec/SpecTree.tsx:57-58`).

So the corpus has a validated, portable, preserved place to record its own shape, and that place has
been empty since it was built.

This is also what makes *"each new spec created needs to reflect a little bit on the main spec"*
affordable. Had every document creation edited shared prose, the result would be tone drift and
write contention on one file. A generated map maintains itself.

## What Changes

- **New**: `render_document` accepts corpus context — the document's home, its parent, and its
  children — and renders two things from it: a **navigation strip** on every document, and a
  **generated map** on any document that has children.
- **New**: the map is generated from `spec/index.json`, listing each child's title, kind, phase and
  summary, linked by relative path. It is never hand-edited.
- **New**: `POST /project/spec/reindex` re-renders the documents whose map or navigation strip the
  rebuilt index changed, and records the new `content_digest` so drift detection does not report the
  Hub's own write as drift.
- **New**: an operator route for setting a document's `parent`, so the arrangement the manifest has
  always preserved can finally be created.
- **Data**: the initial hierarchy is authored once into `spec/index.json` — six area documents under
  the home, and every capability document under an area. `build_index` preserves it from then on.
- Documents with no usable summary render as a stated gap in the map rather than a blank row. Eight
  of the thirty-five qualify today (six empty, two still reading *"TBD - created by syncing change
  … Update Purpose after archive"*).

**Non-Goals** — stated explicitly, not by omission:

- **Not** a product landing screen. The home is a document and stays one; this change makes that
  document say more. A screen is two orders of magnitude more expensive for the same want.
- **Not** injecting the map at view time. A document rendered by the Hub is *"self-contained: inline
  style only, no external resource"* (`hub/hub/spec_render.py:336`), and a corpus whose navigation
  only exists inside the app stops being portable. See design D1.
- **Not** a sibling list on every document. Design D2 explains why that single restraint is what
  keeps the whole change affordable.
- **Not** deriving hierarchy from directory nesting. `build_index` already refuses to, on the stated
  grounds that it *"writes a hierarchy the operator never chose into a file that travels with the
  folder"* (`hub/hub/spec_documents.py:304-307`). That judgement is upheld, not reversed — this
  change gives the operator a way to state the hierarchy instead.
- **Not** changing `SpecTree`'s path-prefix rendering in the rail. The rail is a file tree; the map
  is a document. They answer different questions and this change does not merge them.
- **Not** rewriting the home document's authored narrative. That prose is the operator's and this
  change only appends a generated region beneath it.

## Capabilities

### New Capabilities

- `spec-corpus-map`: how a document learns where it sits in the corpus, what a generated map
  contains, when it is regenerated, and what a reader of the bare file is guaranteed.

### Modified Capabilities

- `spec-document-authority`: gains the rule that a rendered document carries navigation to its home
  and parent, that a document's place in the corpus is operator-set and manifest-held, and that a
  Hub-initiated re-render updates the stored digest rather than manufacturing drift.

## Impact

**Code**

- `hub/hub/spec_render.py` — `render_document` gains a corpus-context parameter; two new render
  helpers (navigation strip, map section); style additions for both.
- `hub/hub/spec_documents.py` — assembling corpus context from a `Manifest`; no change to
  `build_index`'s preservation rule.
- `hub/hub/api/v1/spec.py` — reindex re-renders affected documents; new operator route for `parent`.
- `hub/hub/schemas/` — request/response models for setting a parent and for reporting what
  re-rendered.
- `spec/index.json` — one authored hierarchy edit, then preserved.

**Data**

No migration. `parent` and `order` live in a file, not a column, which is the whole reason they
survive a clone.

**Dependency**

Two of the thirty-five documents on disk — `project-instructions` and `quiet-hours` — have no row,
so `build_index` cannot file them and they cannot be given a parent. They join the map when
`document-adoption` lands. The other thirty-three do not wait on it.

**Risk**

Re-rendering is a write to documents the operator did not ask to change. The bound in design D2 —
navigation is home and parent only, maps render only where there are children — is what keeps a
single new document from rewriting the entire corpus. That bound is worth a test asserting exactly
which files a reindex touched, not only that the map is correct.
