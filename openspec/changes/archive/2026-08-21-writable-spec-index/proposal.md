# Make the specification index writable

## Why

`spec/index.json` is the only thing that gives a specification corpus a home, titles, hierarchy and
ordering, and it is the part that travels with the folder. **It cannot currently be produced**, for
two independent reasons:

1. **Nothing writes it.** Repo-wide, `index.json` appears three times and every one is a read:
   `hub/hub/spec_manifest.py:105` (`load_manifest`), `src/agentweave/spec_manifest.py:147` (the CLI
   twin), and `hub/hub/spec_documents.py:38` (`INDEX_RELATIVE`, consumed by `read_index`).
   `POST /spec/reindex` (`hub/hub/api/v1/spec.py:944`) sounds like the writer but rebuilds the
   *requirement* index in the database via `spec_index.reindex_project` — it never touches the file.

2. **The manifest's vocabulary cannot describe the documents the Hub renders.**
   `submit_spec_document` accepts `kind ∈ {baseline, system-map, roadmap, change-spec, capability}`,
   but `VALID_KINDS` omits `capability` in both twins (`hub/hub/spec_manifest.py:26`,
   `src/agentweave/spec_manifest.py:25`). For status, `hub/hub/spec_render.py:386` writes the
   lifecycle **phase** into `aw-spec-status`, while `_expected_status` (`spec_manifest.py:100`)
   expects a kind-derived constant — `living` for living kinds, `draft`/`approved` for change-spec.

The consequence is total, not partial. Of the three documents in `spec/` today, **none** can be
given a valid manifest entry: the two `capability`/`current` documents fail on kind *and* status,
and the `change-spec`/`archived` document fails because `archived ∉ CHANGE_SPEC_STATUSES`. Because
`load_manifest` returns `None` on any single violation (`spec_manifest.py:210-211`), one bad entry
invalidates the whole file and drops **every** document to `state: "unindexed"` with a
`home_ambiguous` diagnostic (`spec_documents.py:285`, `:314`).

**Why now.** The operator is migrating their development into AgentWeave, starting with the 33
openspec capabilities. Migrating them today would land 33 unindexed documents with no home, no
titles, no hierarchy and no ordering — the corpus would be readable but structureless.

The cause is chronological rather than conceptual: `2026-07-29-add-spec-manifest` predates the
`capability` and `archived` phases (migration `0074_archive_and_capability_phase.py`, 2026-08-16) by
two and a half weeks, and was never reconciled with the lifecycle that shipped after it.

## What Changes

- **`VALID_KINDS` gains `capability`** in both `hub/hub/spec_manifest.py` and
  `src/agentweave/spec_manifest.py`, matching `submit_spec_document`'s enum so there is one kind
  vocabulary rather than two.
- **BREAKING (on-disk format): the manifest's `status` field becomes the lifecycle phase.** The
  kind-derived `living`/`draft`/`approved` model and `_expected_status` are replaced by validation
  against the phase vocabulary `{exploring, proposed, approved, archived, current}`, with a
  kind/phase pairing rule. This aligns `status` with what `spec_render.py:386` already writes into
  `aw-spec-status`, which is what `compute_intrinsic_conflicts` compares it against.
- **A manifest writer is added** — `dump_manifest` in both twins, plus an index-writing step that
  builds entries from the project's `SpecDocument` rows and writes `spec/index.json`.
- **`POST /spec/reindex` writes the index** in addition to rebuilding the requirement index. Its
  docstring already states its purpose as "a project whose documents predate the index"; today it
  does not serve that purpose.
- **`home`, `parent` and `order` are preserved, not clobbered.** Where a valid index already records
  them, the writer carries them forward; where it does not, `order` is derived from a stable sort and
  `parent` is left null. An ambiguous `home` stays unset rather than being guessed, preserving the
  existing requirement that the Hub asks rather than chooses.

**Non-goals.**

- No `parent`/`order` columns on `SpecDocument`, and no UI for arranging documents. The writer
  preserves what it finds; making hierarchy *editable* is a separate change.
- No operator-side content-write or bulk-import route. Authoring stays agent-only and run-bound.
- No delete-document route.
- No migration of the openspec corpus itself. This change unblocks it; it does not perform it.
- No change to discovery, to `_select_home`'s "ask rather than choose" behaviour, or to how
  documents are rendered.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `spec-document-authority`: the index gains a written form. Today's requirements cover only reading
  a manifest that something else was assumed to produce ("An unreadable or absent index degrades
  visibly", `spec.md:353`). This adds the requirement that the Hub can produce a valid index for the
  documents it holds, and fixes the vocabulary so that a document the Hub itself rendered can always
  be described by an index the Hub itself writes.

## Impact

**Code**

- `hub/hub/spec_manifest.py` — `VALID_KINDS`, the status model, `_expected_status`, new
  `dump_manifest`.
- `src/agentweave/spec_manifest.py` — the CLI twin, kept in sync by hand per CLAUDE.md; the two
  intentionally have no import relationship.
- `hub/hub/spec_documents.py` — a `write_index` alongside `read_index`.
- `hub/hub/api/v1/spec.py` — `reindex` writes the manifest and reports what it wrote.

**Data**

- `spec/index.json` in every project — a file that does not exist anywhere today, so there is no
  stored data to migrate. Any hand-written index that used `living`/`draft` statuses would become
  invalid, but none exists: the format has never been writable.

**Tests**

- `hub/tests/` — round-trip (`dump_manifest` → `load_manifest` returns a valid manifest), a real
  rendered document producing zero `intrinsic_metadata_conflict` diagnostics, and the reindex route
  writing a file that `compute_state` then reports as `filed` rather than `unindexed`.
- A twin-sync assertion that both `spec_manifest` modules agree on kinds and phases — the existing
  hand-sync rule has no test today.

**Not affected**

- The Hub's MCP tool surface, the rendering pipeline, and the requirement/evidence/coverage graph.
