## Context

A specification document is a file plus a row. The file is committed and travels; the row is
machine-local and does not. Today there is no way to obtain the row for a file that already exists.

The read path is already file-driven and needs nothing from this change: `GET /specs` builds its
tree from `spec_documents.compute_state()` (`hub/hub/spec_documents.py:393-423`), which walks the
`spec/` directory and reads `spec/index.json`, merging in only `phase` and `document_id` from rows
(`hub/hub/api/v1/spec.py:106-113`). The row-less case is already handled end to end — see
`hub/tests/test_spec_archive.py:125` and the `deriveTitle` fallback in
`hub/ui/src/components/spec/specNavigation.ts:135`.

Everything else is row-keyed, and three separate paths refuse to help:

| Path | What it does | Why it does not solve this |
|---|---|---|
| `POST /documents` (`api/v1/spec.py:1107`) | mints a row, then renders a placeholder over the path | destroys the file it is aimed at |
| `POST /spec/reindex` (`api/v1/spec.py:1036`) | reads files, writes rows | iterates `list_documents()` — rows that already exist |
| `build_index` (`spec_documents.py:245`) | files documents into `spec/index.json` | files *"only documents that are both on disk and known to the Hub"* |

The live consequence: 34 capability documents in `spec/capabilities/`, all 34 carrying a complete
payload block, none with a row; two of them permanently `unfiled`.

**The pieces adoption needs already exist and are already read-only on disk.**

## Goals / Non-Goals

**Goals:**

- Mint a row from an existing file without writing to that file, ever.
- Derive identity from the file: title and kind from its payload, phase from its status metadata.
- Adopt a whole corpus in one call, so a clone reconstitutes.
- Report disagreement between file and row without resolving it.

**Non-Goals:**

- Changing `POST /documents`. Writing a starter file is correct when the document is genuinely new.
- Updating an existing row from its file (re-adoption / refresh). See Open Questions.
- Drift resolution for already-tracked documents — `content_digest` and `POST /spec/drift/detect`
  own that.
- Automatic adoption on a timer or at startup.
- Agent-callable adoption.
- Any database migration. No column is added.

## Decisions

### D1 — A separate route, not a flag on `POST /documents`

**Chosen:** a distinct adoption route. **Rejected:** `POST /documents?adopt=true`.

The failure mode this change exists to prevent is overwriting a document. A flag leaves the
destructive behaviour as the default, one missing parameter away from the safe one. Two routes whose
*names* differ make "create" and "adopt" impossible to confuse, and let the adoption route be
provably free of any write path rather than conditionally free of one.

### D2 — Compose the existing read-only primitives; write no new file reader

**Chosen:** `discover()` → `read_document()` → `extract_payload()` → `create_document()` →
`reindex_from_file()`.

Every one of these already exists and every one is already read-only on disk:

- `spec_documents.discover()` (`:81`) — walks `spec/`, path-safety validated, diagnostics per
  exclusion, capped by `MAX_DISCOVERED_DOCUMENTS`.
- `spec_payload.extract_payload()` (`:297`) — returns `None` rather than guessing when a document
  carries no payload.
- `spec_lifecycle.create_document()` (`:121`) — **pure row-minting; takes no workspace, so it cannot
  touch disk.** This is the property that makes adoption safe by construction rather than by review.
- `spec_index.reindex_from_file()` (`:292`) — reads the file, writes rows only, and already declines
  gracefully on a half-written file rather than retiring its requirements.

**Rejected:** a bespoke adoption parser. It would be a second interpretation of the same file, and
the existing comment on `spec_tasks.materialise` makes the case: the index is rebuilt from the
document's own identity map so it is *"the same source of truth, read the same way — not a second
interpretation of the file."*

### D3 — Title and kind from the payload; phase from the head metadata

The payload block does **not** carry status. Verified against a real corpus document, its keys are:
`acceptance_criteria, algorithms, aw_identity, design, evidence, kind, lifecycle, open_questions,
problem, requirements, schema_version, scope, summary, tasks, title`.

Phase is written only into `<meta name="aw-spec-status">` by `spec_render.py:386`. A reader already
exists — `_SpecHeadParser` (`spec_manifest.py:361`), which extracts `<title>`, `aw-spec-kind` and
`aw-spec-status` and stops at `</head>`.

So adoption reads two places in one file, and the payload wins where both carry a value (`kind`),
because the payload is what the submission actually supplied and the meta tag is its display copy.

**Absent or unrecognised status falls back to the kind-derived default** — `current` for
`capability`, `exploring` otherwise — matching `create_document`'s own rule
(`spec_lifecycle.py:151`). The fallback is *reported*, so a defaulted phase is never mistaken for a
read one.

### D3a — A phase the document's *kind* cannot hold is defaulted, not refused

**Found during implementation, 2026-08-20, and not anticipated by D3.**

D3 says a status naming no known phase falls back by kind. It does not cover a status naming a
phase that is perfectly well known but that *this document* may not be in. The database enforces
`capability ⟺ current` as a cross-column check — `ck_spec_documents_kind_phase`, added by `0074`,
described in `models.py` as *"the strongest available statement that `current` is where capability
documents live and nowhere else"*. So a `system-map` whose file reads `current`, or a `capability`
whose file reads `approved`, describes a row the database will refuse outright.

**Chosen:** treat it exactly as an unrecognised status — fall back to the kind's default, and
report the value the file carried. **Rejected:** refusing the document, which would strand a corpus
over a metadata value the operator can neither see in the app nor easily repair by hand; and
relaxing the constraint, which is load-bearing and predates this change.

The fallback is well-behaved in both directions: a `capability` defaults to `current`, which is the
only phase it could legally have meant, and a non-capability defaults to `exploring`, which is where
creating it would have put it.

`create_document` states the same rule where it takes a `phase`, so the refusal names the problem
instead of arriving as an `IntegrityError` from the flush.

This was invisible against the corpus that motivated the change — all 34 capability documents read
`current`, and `spec/agentweave.html` reads `exploring`, so every real document is already
consistent. It surfaced only from a test corpus containing a `system-map` at `current`.

### D4 — Adoption refuses an already-tracked path, and reports why

**Chosen:** refuse, and report every field on which file and row disagree.
**Rejected:** update the row from the file.

The operator's rule is *"compare with the database, but trust the file."* This change delivers the
comparison and stops short of the resolution, because the resolution collides with a rule stated
twice in the code (`spec_lifecycle.py:130-139`, `spec_render.py:341-345`):

> *"A gate whose value lives where the gated party can write it is not a gate."*

That is why `phase` and `rigor` are columns with only a display copy in the file. Adoption is the
one point where no conflict exists — there is no row yet, so the file is the only thing to trust.
Refuse-and-report gives the operator the diagnostic that would inform the later decision without
pre-empting it.

`compute_intrinsic_conflicts` (`spec_manifest.py`) already compares an index entry against a
document's own `aw-spec-status`; the comparison shape is established.

### D5 — Corpus-wide adoption reports per document and never fails as a whole

One unadoptable document must not abort the other 33. Each path yields adopted-or-skipped with a
stated reason, following `reindex`'s existing response shape (a per-path map plus a diagnostics
list) so the two operations read alike.

Repeatability matters as much as the first run: a second invocation must adopt nothing and report
every path as already tracked, since the natural operator instinct on an unexpected result is to run
it again.

### D6 — `content_digest` is set from the file as found

An adopted document's digest records the file as it was at adoption. This asserts only *"this is
what was adopted"*, which is what later drift detection needs as its baseline. The alternative —
leaving it null — would make the first external edit after adoption undetectable.

### D7 — No change to `spec_manifest.py`, and therefore no twin to synchronise

The head parser adoption needs is already in the Hub's copy. `src/agentweave/spec_manifest.py` and
`hub/hub/spec_manifest.py` are deliberately divergent files (the CLI twin does recursive discovery;
the Hub *"only ever sees uploaded content"*) held together by round-trip agreement tests in
`hub/tests/test_spec_manifest_roundtrip.py`. Touching either would oblige touching both — so this
change touches neither.

## Risks / Trade-offs

**Adoption writes to a file** → The whole point of the change is that it cannot. `create_document`
takes no workspace and is structurally unable to; the test must assert **file bytes are unchanged**,
not merely that a row appeared. A test that only checks the row would pass against the current
destructive behaviour.

**A partially-adopted corpus** → Corpus-wide adoption over 34 documents that fails at document 20
leaves 19 adopted. Mitigated by D5's per-document reporting and by repeatability: re-running adopts
the remainder and reports the rest as already tracked.

**A phase read from a file the operator did not write** → An adopted document arrives claiming a
phase. For the corpus at hand this is inert (all `capability`/`current`), but the rule outlives the
corpus. Mitigated by scope: adoption happens once per document, at the operator's request, and the
row is authoritative from then on.

**Adoption becomes a back door to phase promotion** → Only if re-adoption is later built without
resolving the collision in D4. Recorded here so that decision is taken deliberately.

**`MAX_DISCOVERED_DOCUMENTS` silently truncates a large corpus** → `discover()` already caps and
reports truncation; corpus-wide adoption must surface that diagnostic rather than presenting a
truncated sweep as complete.

## Migration Plan

No database migration; no schema change; no data backfill.

Deployment is inert until invoked — adoption does nothing on its own. The rollback is to stop
calling it; rows already created are ordinary document rows and are not distinguishable from, nor
more fragile than, rows created through `POST /documents`.

**First real use** is this repository's own corpus: 34 documents in `spec/capabilities/`, plus
`spec/agentweave.html`, none currently tracked. That is the acceptance test the operator will
actually run.

## Open Questions

1. **Re-adoption / refresh-from-file.** Deferred by D4. Needs the "trust the file" versus "a gate
   whose value lives where the gated party can write it" collision resolved first —
   `openspec/explorations/2026-08-20-the-row-is-the-spine.md` §9 proposes reading file-authority as
   *at the boundary* rather than *always*, which would let refresh be an explicit operator act that
   re-crosses the boundary.
2. **Does adoption set `rigor`?** The file carries `aw-spec-rigor` and the row has a `rigor` column
   defaulting to `sketch`. The same argument as phase applies, but rigor is a live gate on current
   work in a way an adopted document's phase is not.
3. **Should corpus-wide adoption run reindex itself,** or leave the operator to run it after? Two
   calls is more predictable; one is fewer steps for the case that motivated this change.
