## Why

A specification document is a file on disk plus a row in `spec_documents`. The read path already
works from the file alone — `GET /specs` walks `spec/` and returns every document it finds
(`hub/hub/spec_documents.py:393-423`), so a corpus is browsable without any database state. Every
other capability — phase, requirements, coverage, evidence, task materialisation — is keyed on the
row.

There is no way to obtain that row for a file that already exists. `POST /documents` mints the row
and then immediately renders a placeholder over the path
(`hub/hub/api/v1/spec.py:1141-1153`, `"title": body.title or UNTITLED`), so pointing it at an
existing document destroys the document. `POST /spec/reindex` reads files and writes database rows,
but iterates `list_documents()` — rows that already exist (`hub/hub/spec_index.py:318-331`). And
`build_index` files *"only documents that are both on disk and known to the Hub"*
(`hub/hub/spec_documents.py:257`), so a file with no row can never enter `spec/index.json` either.

The consequence is concrete and current: 34 capability documents live in `spec/capabilities/`, all
34 carrying a complete `id="aw-spec-payload"` block, and none of them has a row. Two —
`project-instructions` and `quiet-hours` — are permanently `unfiled` for exactly this reason. The
corpus is readable and inert.

This is also the permanent on-ramp, not only a migration tool. A repository cloned to another
machine arrives with files and no database, because the row never leaves the machine that made it.

## What Changes

- **New**: adopt an existing document — create a `spec_documents` row from a file already on disk,
  deriving title, kind and phase from the file's own embedded payload, and **never writing to the
  file**.
- **New**: adopt a whole corpus in one operation, so a cloned or migrated project is recoverable
  without 34 individual calls.
- Adoption **reports** every field where the file disagreed with an existing row rather than
  resolving silently, per the operator's rule: compare with the database, trust the file.
- A file carrying no readable payload block is **refused**, not guessed at — consistent with
  `extract_payload` returning `None` rather than inventing (`hub/hub/spec_payload.py:297-303`) and
  with `build_index` refusing to invent a title (`hub/hub/spec_documents.py:271-273`).
- Adopted documents become indexable, so a subsequent `POST /spec/reindex` files them into
  `spec/index.json` with their real titles instead of reporting `unindexable_document`.

**Non-Goals** — stated explicitly, not by omission:

- **Not** splitting or changing `POST /documents`. It stays exactly as it is: the way to start a
  *new* document, where writing a starter file is correct.
- **Not** resolving drift for documents that already have rows. Adoption is the boundary crossing
  from no-row to row; `content_digest` and `POST /spec/drift/detect` keep owning the case where a
  row exists and the file moved underneath it.
- **Not** re-adoption or refresh-from-file for an already-adopted path. That re-crosses the
  boundary and depends on the unresolved collision between "trust the file" and *"a gate whose value
  lives where the gated party can write it is not a gate"* (`hub/hub/spec_lifecycle.py:130-139`).
  Adoption sits on the side where the file wins under either reading.
- **Not** automatic adoption on a timer or at startup. Reading every file to detect the need is
  precisely why reindex is *"offered rather than guessed at on a timer"*
  (`hub/hub/api/v1/spec.py:1046-1047`).
- **Not** agent-callable. Adoption is an operator act in this change.

## Capabilities

### New Capabilities

- `spec-document-adoption`: creating a Hub-tracked document from a file that already exists,
  deriving its identity from the file's own payload, without modifying the file; and the corpus-wide
  form of the same operation.

### Modified Capabilities

- `spec-document-authority`: gains the rule that a document may enter Hub tracking without being
  created through the Hub, and that its title, kind and phase are then derived from the file rather
  than supplied by the caller.

## Impact

**Code**

- `hub/hub/api/v1/spec.py` — new route(s); no change to `POST /documents`.
- `hub/hub/spec_lifecycle.py` — `create_document` is reused unchanged; it is already pure
  row-minting and takes no workspace, so it cannot touch disk.
- `hub/hub/spec_index.py` — `reindex_from_file` reused unchanged (already read-only on disk).
- `hub/hub/spec_documents.py` — `discover()` reused for the corpus-wide form.
- `hub/hub/schemas/` — request/response models for the adoption result and its disagreement report.

**Data**

- New `spec_documents` rows only. No migration: no column is added by this change.

**Downstream, unblocked but not delivered here**

Requirements, coverage, evidence, phase transitions and task materialisation all key on
`SpecDocument.id` and become reachable for the existing corpus once rows exist.

**Risk**

The failure this change exists to prevent is writing over a document. Every path must be provably
read-only on disk, and that property is worth a test that asserts file bytes are unchanged rather
than only asserting the row appeared.
