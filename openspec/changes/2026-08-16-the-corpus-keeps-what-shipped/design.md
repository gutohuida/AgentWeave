# Design — The corpus keeps what shipped

## D1. Two new phase values, one new transition, enforced where approval already is

`SPEC_PHASES` becomes `("exploring", "proposed", "approved", "archived", "current")`.

`TRANSITIONS` gains exactly one entry: `(APPROVED, ARCHIVED)`. Nothing transitions into or out of
`CURRENT` — a capability document is created there (D2) and a capability document is never proposed,
approved, reopened or archived through `transition()`.

`transition()` gains the same shape of check it already has for approval:

```python
if to_phase == ARCHIVED and actor.kind != "operator":
    raise PhaseError("only the operator can archive a document", code="archive_is_the_operators")
```

placed beside the existing `to_phase == APPROVED` check, for the same reason the module's own
docstring gives for approval: *"a rule enforced in one place is a rule that survives exactly as long
as nobody adds a second caller."* This is also why `to_phase not in (EXPLORING, PROPOSED, APPROVED)`
(the unknown-phase guard) becomes `to_phase not in (EXPLORING, PROPOSED, APPROVED, ARCHIVED)` —
deliberately **not** including `CURRENT`. A caller reaching `transition()` with `to_phase="current"`
is refused as an unknown phase for `transition`'s purposes, because `current` is not a phase anything
transitions *to* — it is where a capability document already is from the moment it exists. The one
door into `current` is document creation (D2), not this function.

**Why `(APPROVED, ARCHIVED)` only**, no path from `exploring` or `proposed`. An abandoned exploration
or an abandoned proposal is a different situation from a finished, shipped change, and the existing
`(PROPOSED, EXPLORING)` / `(APPROVED, EXPLORING)` reopening already gives an operator a way to walk a
document backwards without inventing a second kind of "done." Scoping archival to documents that were
actually approved keeps `archived` meaning one thing: *this was approved, and now its work is
finished.*

**Why no `(ARCHIVED, *)` transition.** Once a document is archived it is meant to be read, not decided
about further — the same reasoning `approved` already carries for ordinary edits (see D2's reuse of
the existing `save_document` refusal). Proposal.md's Non-Goals records this as a deliberate omission,
not an oversight; nothing in this session's evidence needs it reversed.

## D2. Capability documents: created at `current`, written only by merge

`spec_lifecycle.create_document` picks the initial phase from `kind` rather than always starting at
`EXPLORING`:

```python
phase = CURRENT if kind == "capability" else EXPLORING
```

This is the one and only place a document's phase is ever set to `current`. Everything downstream —
`transition()`, `close_exploration()`, `propose()` — already only operates on documents it is handed,
and none of them is ever called against a capability document by any UI or agent path this change
adds, because there is nothing for those actions to do to a document with no transitions.

**Content.** `spec_service.save_document` gains one refusal, checked before the existing
`document.phase == APPROVED` refusal:

```python
if document.kind == "capability" and actor.kind != "operator":
    raise SaveRefusedError(
        "capability documents are written by the operator, through a merge",
        code="capability_write_is_the_operators",
    )
```

This is enforced in `save_document` itself — the function every write path funnels through — rather
than only at whichever route happens to call it today, for the identical reason D1 gives for
archiving. Concretely, it means the agent's `submit_spec_document` route
(`hub/hub/api/v1/agent_actions.py:1100`) starts refusing on any capability document, with no change to
that route's own code required: the refusal already lives one layer down, where nothing can route
around it.

**Why the operator writes capability content through `save_document` at all**, rather than a
dedicated, simpler write path. Reuse: `save_document` already does everything a capability write needs
— payload validation, requirement identity minting (so a capability document's requirement keys are
stable across an edit exactly the way a change document's are), digesting, rendering, indexing. A
second, parallel implementation of all of that for capability documents specifically would be the
architectural mistake this session's own brief warns N3 against, applied to N2 instead.

**Correcting N1's recommendation 1.** N1 read `openspec/specs/<capability>/spec.md` (absolute
requirements) against a change's `specs/<capability>/spec.md` delta (`## ADDED/MODIFIED/REMOVED
Requirements`) and concluded a capability document needs a distinct payload schema. Reading
`spec_payload.py` (not the openspec file convention) shows the Hub's `SpecPayload` has never modelled
a delta at all — `requirements: List[Requirement]` is a flat, absolute list for every `kind` that has
ever been submitted through the Hub, `change-spec` included. There is nothing to discriminate: a
capability document's payload is the exact shape a change document's already is. **No schema change is
needed for D2 to work.** What actually distinguishes the two is everything else in this design —
phase, write authority, and the merge record — not the payload's shape. `KINDS` in `spec_payload.py`
gains `"capability"` as a valid value (task 4.4) so a submission can name it; nothing about
`SpecPayload` itself changes.

**Round 2 correction.** Round 1's `tasks.md` stated this in prose here but never turned it into a
checklist item — a real gap, not a stylistic one: `validate_payload` refuses any `kind` outside
`KINDS` before either D2's or D3's refusal ever runs, and the *unchanged* `create_document` route
already calls `save_document` right after creating a document, of any kind, to write its initial
scaffold. Skipping this would mean creating a capability document — not merging into one, just
creating it — fails immediately with `payload_invalid`. Added as task 4.4.

## D3. `kind` is pinned at creation

Reading `record_content` (`spec_lifecycle.py:145`) and its one caller, `save_document`
(`spec_service.py:124-132`): every content submission passes `kind=payload.kind`, and
`record_content` sets `document.kind = kind` unconditionally. A document's `kind` today is not fixed
at creation — it is whatever the *most recent submitted payload* said, agent-authored payloads
included.

This was always a latent defect (a submission carrying the wrong `kind` silently reclassifies a
document nobody asked to reclassify) and becomes a correctness hole once `kind` decides which phase a
document is allowed to be in: an agent's submission that happened to carry `kind: "roadmap"` against a
`change-spec` document would previously have been a cosmetic mislabel. Fixed now, not filed
separately — shipping the phase/kind coupling without this would let the coupling be defeated by the
exact caller (an agent submission) the coupling exists to keep out.

**Fix**: `save_document` refuses a payload whose `kind` differs from `document.kind`, before any other
work:

```python
if payload.kind != document.kind:
    raise SaveRefusedError(
        f"this document is {document.kind!r}; a submission cannot change what a document is",
        code="kind_is_fixed",
    )
```

`record_content` stops accepting `kind` as a parameter — there is nothing left for it to vary, since
the caller has already asserted equality. (`create_document` still sets the row's `kind` once, at
creation, from `DocumentCreate.kind` — the one legitimate place `kind` is chosen.)

## D4. The merge record

New table, `spec_document_merges`: one row per (change document, capability document) pair an
operator has folded together.

```python
class SpecDocumentMerge(Base):
    __tablename__ = "spec_document_merges"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    capability_document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("spec_documents.id"), nullable=False
    )
    change_document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("spec_documents.id"), nullable=False
    )
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    note: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    __table_args__ = (
        CheckConstraint("actor_kind = 'operator'", name="ck_spec_document_merges_actor_is_operator"),
        Index("ix_spec_document_merges_capability", "capability_document_id", "created_at"),
        Index("ix_spec_document_merges_change", "change_document_id", "created_at"),
    )
```

**Why a table over the JSON `detail` field N1 §2 left open.** `spec_document_events.detail` is
unindexed JSON; "every change that touched capability X" or "what did change Y's merge do" would both
be table scans over every event row in the project, forever, growing without bound. A dedicated table
with two indexes answers both directions in a normal query, and it is the same shape every other
append-only fact in this schema already takes (`SpecRigorEvent`, `EvidenceReview`, `TaskTransition`) —
not a new pattern, a fourth instance of one.

**Why `CHECK actor_kind = 'operator'`**, stronger than the generic `actor_kind IN (...)` every other
actor-kind column in this file uses. This table exists *because* the operator's authorship is the
point — unlike an ordinary event log, which records whoever acted, a merge row that could record an
agent's actor_kind would be recording the exact act D2 exists to keep an agent from performing. The
CHECK makes the invariant true even against a caller that reaches the table directly, not only against
the one route this change adds.

**One event, not two.** The merge is also recorded as a `spec_document_events` row on the *capability*
document (`kind="merged"`, `detail={"change_document_id": ..., "note": ...}`), reusing the existing
per-document event stream a reader already knows to look at when reading one document's history. No
matching event is written on the change document's side — `spec_document_merges` already answers "what
did this change's merge do" by querying `change_document_id`, and a second copy of the same fact in a
second place is exactly the kind of drift risk `requirement_coverage.py`'s own docstring warns against
("a second implementation ... is exactly the thing this change exists to prevent").

## D5. The merge endpoint

`POST /project/documents/{path:path}/merge`, operator-only (this router already requires the project
credential; see `spec.py`'s existing routes), body:

```python
class MergeRequest(BaseModel):
    payload: Dict[str, Any]           # same shape submit_spec_document accepts
    from_changes: List[str] = Field(min_length=1, max_length=16)  # change document paths
    note: str = Field(default="", max_length=2000)

    model_config = {"extra": "forbid"}
```

Handler, in order — every refusal before anything is written, the same discipline `rename_document`
already follows:

1. Resolve the capability document by `path`; 404 if absent.
2. Refuse (409, `code="not_a_capability"`) if `document.kind != "capability"`.
3. Resolve each `from_changes` path to a document in this project; 404 naming the missing one if any
   is absent.
4. Refuse (409, `code="source_not_finished"`) if any resolved source document's `phase` is not one of
   `APPROVED`, `ARCHIVED` — a merge names a *finished* change (proposal.md's Non-Goals: merge and
   archive are independent, but a merge still may not cite work still being decided about).
5. Call `spec_service.save_document(session, workspace, document, body.payload, actor=_operator())` —
   the same function every other content write uses; D2 and D3's refusals apply exactly as they would
   to any other caller, so a malformed or misclassified payload is refused here identically to
   everywhere else, not by a second, looser check.
6. For each resolved source document, insert one `SpecDocumentMerge` row and record one `merged` event
   on the capability document (D4).
7. Commit; broadcast `spec_updated` for the capability document's path.

**`from_changes` takes paths, not database ids.** Every existing document-scoped route in `spec.py`
(`{path:path}` routes, `_require_document`) already resolves by path; a merge request naming ids would
be the one place in this router that broke that convention, for a caller (the operator, in the UI)
who is looking at paths, not ids.

## D6. Migration `0074`

Two independent pieces, one migration file, both guarded for a missing `spec_documents` /
`projects` table the way `0058`/`0065`/`0073` are (an upgrade starting from an early revision reaches
`0074` with only the tables those revisions created; `create_all` builds the rest from the model on a
fresh database).

**Piece 1 — recreate `spec_documents`.** `batch_alter_table("spec_documents", recreate="always")`:

- Drop and recreate `ck_spec_documents_phase` with the five-value list.
- Add `ck_spec_documents_kind`, a new CHECK restricting `kind` to the vocabulary that has ever actually
  been declared valid — `spec_payload.KINDS` (`baseline`, `system-map`, `roadmap`, `change-spec`) plus
  `capability`. `kind` has never been constrained at the database layer before this; adding the
  constraint now, in the same recreate that is already touching this table's CHECKs, costs nothing
  extra and closes the other half of the hole D3 closes at the Python layer.
- Add `ck_spec_documents_kind_phase`: `(kind = 'capability' AND phase = 'current') OR (kind !=
  'capability' AND phase != 'current')`. A cross-column CHECK is not a new idiom in this schema — `0058`
  already ties `origin_type` and `origin_agent` together the same way for exactly the same reason: an
  invariant that matters is worth enforcing somewhere a bug in application code cannot quietly violate
  it. This is the strongest statement available of "current is where capability documents live and
  nowhere else" — stronger than D1's `transition()` guard alone, which only stops the phase machine
  from producing the mismatch and says nothing about a row inserted some other way.

**Piece 2 — create `spec_document_merges`.** A plain guarded `op.create_table`, no recreate: the table
is new, so there is no existing CHECK to fight SQLite's in-place-ALTER limitation on. Follows `0065`'s
`spec_document_events` exactly (same guard function, same shape of `CheckConstraint` and `Index` calls
inline in the `create_table`).

**Downgrade.** Piece 2 drops the indexes then the table. Piece 1 restores the three-value phase CHECK
and drops the two new CHECKs — but only after reassigning any row that downgrade would otherwise leave
violating the restored constraint: `archived` rows become `approved` (the state they were in
immediately before archiving, which is recoverable information — every archive event records the prior
phase, per `record_event`'s existing `detail={"from": previous, ...}"`), and `current` rows become
`approved` (the closest existing phase to "settled, not being decided about," mirroring `0058`'s own
downgrade choice of mapping a retired value to the nearest existing one rather than inventing new
downgrade-only behaviour).

## D7. UI

**`SpecPhaseBar.tsx`** (`hub/ui/src/components/spec/SpecPhaseBar.tsx`):

- The existing "Reopen" button's condition, `document.phase !== 'exploring'`, is a latent bug once
  `archived` and `current` exist: it would offer a control that always fails, since neither phase has a
  transition to `exploring`. Narrowed to `document.phase === 'proposed' || document.phase ===
  'approved'` — the only two phases that actually have one.
- New "Archive" button, shown only when `document.phase === 'approved'`, calling the existing
  `useSetSpecPhase` mutation with `to: 'archived'` — no new mutation hook needed, `set_phase` already
  accepts any phase and `transition()` is what changed.
- The phase chip (`data-testid="spec-phase"`) keeps rendering `document.phase` verbatim — `archived`
  and `current` are legible words on their own — but picks up a visually muted treatment for both,
  consistent with them being phases nobody is actively deciding about (as opposed to `exploring` /
  `proposed`, where a decision is pending).
- `current` shows neither "Reopen" nor "Archive" nor "Approve" nor "Exploration is complete" nor
  "Propose" — every existing conditional in this file is already gated on a specific phase name, so a
  capability document simply matches none of them and the bar renders only the chip and the rigor
  control. No new conditional needed to *suppress* controls; only the "Reopen" narrowing above, which
  was already necessary for `archived`.

**No merge UI in this change.** The merge endpoint (D5) ships with no dedicated screen — proposal.md's
Non-Goals already scopes this change to the mechanism, not the drafting workflow. Exercising it this
session is via the API directly (task 8, human-only verification), the same way `record_evidence` and
several other operator-only routes shipped before their UI did.

## D8. What this leaves for N2b

Everything here leaves `Task.spec_document_id`, `Task.spec_task_key`, and every existing task row
untouched. Archiving a document changes exactly one column on exactly one `spec_documents` row — no
task is read, written, or reclassified by anything in this change. N1 §5's recommendation (the board's
*default view* excludes a terminal task whose declaring document is archived) is explicitly **not**
built here: it is a `tasks` list-query concern, N2b's brief owns it, and proposal.md's Non-Goals says
so. What this change does provide for N2b to build against: `document.phase == 'archived'` is now a
real, queryable fact a task-list filter can join against.
