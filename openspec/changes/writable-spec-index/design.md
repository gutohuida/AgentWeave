## Context

`spec/index.json` is the manifest that gives a specification corpus its home document, titles,
hierarchy and ordering. Unlike the requirement/evidence/coverage graph — which is per-database rows
— the manifest is a plain file, so it is the part of a corpus's *structure* that travels with the
folder when a project moves between machines or Hubs.

It has never been writable. Two facts, established by reading the code rather than the docs:

- **No writer exists.** `index.json` appears three times repo-wide and all three are reads:
  `hub/hub/spec_manifest.py:105`, `src/agentweave/spec_manifest.py:147`, `hub/hub/spec_documents.py:38`.
  `POST /spec/reindex` (`hub/hub/api/v1/spec.py:944`) rebuilds the requirement index in the database
  via `spec_index.reindex_project`; it never touches the file.
- **The schema cannot describe the Hub's own output.** `VALID_KINDS` omits `capability`
  (`spec_manifest.py:26`), and `_expected_status` (`:100`) derives status from kind — `living` for
  baseline/system-map/roadmap, `draft`/`approved` for change-spec — while `spec_render.py:386` writes
  the lifecycle **phase** into the rendered document's `aw-spec-status`.

`compute_intrinsic_conflicts` (`spec_manifest.py:295`) compares those two fields directly, so the
divergence is not merely cosmetic: it is compared, and it always disagrees.

The cause is chronological. `2026-07-29-add-spec-manifest` shipped before the `capability` and
`archived` phases (migration `0074_archive_and_capability_phase.py`, 2026-08-16). The manifest was
never revisited when the lifecycle grew.

**The forcing constraint.** The operator is migrating 33 openspec capabilities into `spec/`. Every
one of them is a `capability` document — precisely the kind the manifest cannot express. Without
this change the migration produces 33 documents at `state: "unindexed"` with a `home_ambiguous`
diagnostic and no structure at all.

## Goals / Non-Goals

**Goals:**

- A corpus the Hub rendered can always be described by an index the Hub validates. No document the
  product can produce should be inexpressible in the product's own manifest.
- One kind vocabulary, shared with `submit_spec_document`, rather than two that drift.
- `status` in the index means the same thing as `aw-spec-status` in the document — the lifecycle
  phase — so `compute_intrinsic_conflicts` compares like with like.
- A writer, reachable by the operator, that turns "documents exist" into "documents are filed".
- Rebuilding is safe to repeat: it preserves arrangement rather than flattening it.

**Non-Goals:**

- Making hierarchy editable. `parent` and `order` get no columns and no UI here; the writer
  preserves what it finds and derives the rest.
- An operator content-write or bulk-import route. Authoring stays agent-only and run-bound —
  correctly, since that is what makes authorship attributable.
- A delete-document route.
- Performing the corpus migration. This change unblocks it.
- Any change to discovery, rendering, or `_select_home`'s "ask rather than choose" behaviour.

## Decisions

### 1. `status` becomes the lifecycle phase, replacing the kind-derived model

`_expected_status` and the `living`/`draft`/`approved` model are removed. An entry's `status` is
validated against the phase vocabulary `{exploring, proposed, approved, archived, current}`.

*Alternative rejected — keep both and translate at the boundary.* A translation layer would need a
total mapping between a 3-value kind-derived vocabulary and a 5-value lifecycle, and no such mapping
exists: `current` and `exploring` have no kind-derived counterpart, and `living` has no phase. The
translation would have to invent values, which is how the two drifted in the first place.

*Alternative rejected — make the renderer emit the kind-derived status instead.* This would make the
manifest self-consistent by making the rendered document lie about its phase. The phase is the more
useful fact and is already what the rest of the system reasons about.

**This is a format break, but there is no data to break.** The format has never been writable, so no
`index.json` written by the product exists anywhere. A hand-written one using `living` would become
invalid; none is known to exist, and the repo's own `spec/` has no index at all.

### 2. Kind and phase are validated as a pair, not independently

Derived from the phase machine rather than asserted:

| kind | permitted phases | why |
|---|---|---|
| `capability` | `current` only | `create_document` puts it at `current`, and `transition()` accepts no `to_phase` from it — `TRANSITIONS` (`spec_lifecycle.py:38`) contains no pair whose source is `current`, and `current` is rejected as a destination at `:221`. A capability document therefore never leaves `current`. |
| `baseline`, `system-map`, `roadmap`, `change-spec` | `exploring`, `proposed`, `approved`, `archived` | created at `exploring` (`create_document`) and walk the transition table. |

Validating the pair rather than each field catches an index that is individually well-formed but
describes a document that cannot exist — a capability marked `approved`, say, which would look
plausible to a reader and is unreachable in the product.

### 3. The writer lives in `spec_manifest`, and the file-touching wrapper in `spec_documents`

`dump_manifest(manifest) -> str` goes in both `spec_manifest` twins, beside `load_manifest`, and is
pure: manifest in, JSON text out, no filesystem. `write_index(workspace, manifest)` goes in
`spec_documents` beside `read_index`, and is the only thing that touches disk — through
`ProjectWorkspace.resolve_relative`, like every other path in that module.

This keeps the round-trip property (`load_manifest(dump_manifest(m)) == m`) testable without a
filesystem, and keeps the CLI twin — which has no `ProjectWorkspace` — able to carry the same
serialisation.

*Alternative rejected — put the writer only in the Hub.* The twins exist so the CLI can validate a
manifest locally. A CLI that can read a format it cannot write is the asymmetry that let this bug
survive; both should be able to round-trip.

### 4. `reindex` writes the index, and stays the operator's

`POST /spec/reindex` already depends on `get_project` and is documented as "The operator's, not an
agent's" for exactly the case at hand — "a project whose documents predate the index". It gains the
manifest write and reports what it wrote alongside the requirement-index results.

*Alternative rejected — a new dedicated route.* Two operator routes that both mean "make the index
match the files" would need an explanation of when to use which, and the existing one's docstring
already promises this behaviour. Better to make the route true than to add a second.

The agent-facing surface gains nothing: no MCP tool writes the index. Presentation is an operator
decision, and this keeps that boundary where the rest of the phase machine already puts it.

### 5. Arrangement is preserved; only what is missing is derived

The writer reads the existing index first. For each document still on disk it carries forward the
recorded `parent` and `order`; for `home`, a recorded home that still exists is kept.

What is missing is derived conservatively:

- `order` — a stable sort by path, so two rebuilds with no intervening change produce identical
  files. Deliberately not creation order: `SpecDocument.created_at` would make the file's contents
  depend on database rows that do not travel with the folder.
- `parent` — left `null`. Deriving parentage from directory nesting is tempting and wrong:
  `spec/capabilities/foo/spec.html` and `spec/changes/bar/spec.html` share no meaningful parent
  document, and inventing one would put a hierarchy the operator never chose into a file that
  outlives this machine.
- `home` — left unset when ambiguous. `_select_home` (`spec_documents.py:256`) already refuses to
  choose, with the reasoning that a guess is indistinguishable from an operator's decision. The
  writer must not smuggle in the choice the reader declines to make.

A recorded home naming a document that no longer exists is **not** replaced. That preserves
`_select_home`'s existing `home_missing` diagnostic rather than silently healing a broken index,
which would hide the deletion that caused it.

### 6. Twin agreement gets a test, because nothing else can hold it

CLAUDE.md requires the two `spec_manifest` modules be kept in sync by hand and states they
intentionally have no import relationship. That rule has no test today, and this change is direct
evidence of what that costs: both twins carry the identical `VALID_KINDS` omission.

A test asserts the two modules expose the same kind and phase sets. It imports both, which is the
one place an import between them is legitimate — a test's job is to observe both sides.

## Risks / Trade-offs

- **A corpus with no `home` still renders no home.** → Deriving one is explicitly rejected above, so
  a multi-document project stays `home_ambiguous` until the operator picks. The migration will hit
  this immediately with 33 documents. Mitigated by the diagnostic already being explicit about what
  it wants; setting a home is a follow-on UI concern, and the index becoming *writable* is what makes
  that UI possible at all.
- **Flat hierarchy on import.** → 33 documents with `parent: null` lose the grouping the openspec
  directory implied (`agent-*`, `spec-*`, `project-*`). Accepted for now: a wrong hierarchy written
  into a travelling file is worse than none, and `order` at least keeps them stable and predictable.
- **Format break with no migration path.** → Mitigated by there being no data: the format was never
  writable. Should a hand-written index exist somewhere, it fails loudly as `invalid` and the
  documents are still listed — the existing "degrades visibly" requirement covers exactly this.
- **The pairing table encodes today's phase machine.** → If a future change lets a capability be
  archived, the table must move with it. Mitigated by deriving the table from the lifecycle
  constants rather than restating the strings, so a new transition surfaces as a failing test rather
  than a silently over-strict index.

## Migration Plan

1. Vocabulary and validation in `hub/hub/spec_manifest.py`, then mirror into
   `src/agentweave/spec_manifest.py`.
2. `dump_manifest` in both twins; round-trip test.
3. `write_index` in `spec_documents.py`.
4. Wire into `reindex`; extend its response.
5. Run against this repo's own `spec/` — three documents, two `capability`/`current` and one
   `change-spec`/`archived` — and confirm all three report `filed` with zero
   `intrinsic_metadata_conflict` diagnostics. This repo is the first real test case.

**Rollback:** the change is additive to disk. Deleting a written `spec/index.json` returns a project
to `index: absent`, which is exactly today's state and is already handled.

## Open Questions

- **RESOLVED during implementation — how does the operator name a home?** The two questions below
  turned out to be one blocker, and it was worse than "deferred": with several documents and no
  recorded home, `build_manifest` correctly refuses and the writer produces **nothing at all**. A
  33-document corpus would have hit this on document two, so the change as originally scoped could
  not have unblocked the migration it exists for.

  `POST /spec/reindex` now accepts an optional `home`. An explicit home wins over a recorded one
  (the operator is answering now); absent it, a recorded home is preserved and a single-document
  corpus still resolves itself on read, as `_select_home` already did. Nothing is guessed.

- **Still open: there is no way to set a home from the app.** The API can answer the question; the
  UI cannot ask it. "Set as home" on a document in the spec tree is the obvious shape. Deliberately
  not built here — it is a UI change and this slice was already deep — but it is the difference
  between a corpus that indexes itself and one that needs a curl command. Recorded as finding 8 in
  `openspec/explorations/2026-08-20-dogfooding-findings.md`.

- **Should `parent` and `order` become columns?** The writer establishes that the index file is
  currently the *only* copy of both, which makes it authoritative by accident rather than by design
  (finding 10). Promoting them would make a rebuild safe by construction. Out of scope; it needs the
  arranging UI to exist first, or there is nothing to store.
