# The corpus keeps what shipped

## Why

**A document that reaches `approved` has nowhere left to go, and nothing distinguishes "what we
decided to build" from "what the product does today."**

`hub/hub/spec_lifecycle.py` defines exactly three phases — `exploring`, `proposed`, `approved` — and
a four-entry transition table with no exit from `approved` except back to `exploring`. That is a
complete model of *deciding to change something*. It has no model at all of the record that should
exist once the change has shipped: a document nobody is deciding about any more, that simply states
what a capability does. `SpecDocument.kind` has carried a `String(32)` since it was added
(`models.py:1537`, default `'change-spec'`) and — verified by reading every caller this session — has
never been set to anything else in practice, even though the column technically accepts any string.
The slot exists; the second meaning does not.

This is the gap CLAUDE.md names as the reason openspec still keeps the corpus of 30 shipped-capability
documents and 67 archived changes: *"AgentWeave's lifecycle is exploring → proposed → approved with no
archive phase and no concept of a current-behaviour specification. A document reaches approved and
stops."* Closing it is what makes the eventual move off openspec possible at all — not an improvement
alongside the spec flow, but the one piece of it that has been missing since the flow shipped on
2026-08-12.

`openspec/explorations/2026-08-16-a-corpus-at-scale.md` (N1 in this session's run) answered, with
evidence from this repository rather than in the abstract, what the corpus needs at scale: an archive
transition, a capability document kind, and an authored-merge record connecting a finished change to
the capability document(s) it changed. This proposal builds exactly that, and no more — the task board
at scale is a separate, contingent item (N2b) that this change deliberately leaves room for rather than
also solving.

One correction to N1 made while grounding this proposal in the actual payload code (not only the
openspec file convention it read): **the Hub's structured payload has exactly one requirement shape —
a flat, absolute list — for every document kind today.** There is no ADDED/MODIFIED/REMOVED delta
schema anywhere in `spec_payload.py`; that convention is an openspec-markdown-file artifact this
change's own `specs/` delta below uses, not something the Hub's JSON payload has ever modelled. N1's
recommendation 1 read as "capability documents need a distinct schema" from the *file* evidence; the
*code* evidence says a capability document needs no new schema at all, because every document's
payload is already the absolute shape a capability document wants. This proposal is scoped to that
correction — see Design D2.

## What Changes

- **A fourth and fifth phase value.** `archived` — a change document's terminal state once its work is
  done and (typically, though not necessarily first) merged into the corpus. `current` — the phase a
  capability document occupies from creation and never leaves. Both join
  `ck_spec_documents_phase`; both need a table recreation to add, exactly as `0058` and `0073` needed
  for their own CHECK constraints.
- **Archiving is an operator act, enforced inside `spec_lifecycle.transition` itself** — the same
  function, the same enforcement shape, as the existing rule that only an operator can approve. No
  second gate, no UI-only check.
- **`kind='capability'` is a real second meaning**, not a second string. A capability document is
  created directly in `current`, never passes through `exploring`/`proposed`/`approved`, and — this is
  new, not merely inherited — **its content can only be written by an operator, through an explicit
  merge**, never by an agent's ordinary `submit_spec_document`. This is what makes "the corpus absorbs
  a finished change by explicit authored merge" true in code rather than true by convention: the same
  authority question as "an agent cannot approve," applied to the record an agent has the least
  business rewriting unsupervised.
- **A document's `kind` is pinned at creation.** Reading `spec_service.save_document`, every content
  submission — including an agent's — currently overwrites `SpecDocument.kind` with whatever the
  submitted payload's own `kind` field says, unvalidated against what the document was created as. That
  is a latent defect on its own (a submission with the wrong `kind` silently reclassifies the document)
  and becomes an active one once `kind` governs which phase a document can be in: an accidental
  `kind` drift on an ordinary change document would not previously have mattered; now it would let a
  document's `kind` and `phase` disagree about what the document is. Fixed here, not filed separately,
  because leaving it unfixed would undermine the very invariant this change adds.
- **A merge record**, `spec_document_merges`: one row per (change document, capability document) pair
  an operator has folded together, recording who did it, when, and any note — queryable both ways
  ("what has touched this capability" and "what did this change's merge do"), which is the index N1 §2
  asked for without a folder reorganisation.
- **No folder reorganisation.** Per N1 §2 and §6: `openspec/specs/` and `openspec/changes/archive/`
  both stay exactly as they are. This proposal changes what the Hub's own data model can represent; it
  does not touch how `openspec/` is laid out, and this session's change is Hub-side machinery the
  `openspec-*` skills do not yet call.
- **UI**: an "Archive" action beside "Approve" on an approved document; the existing "Reopen" button —
  today shown for any phase other than `exploring`, a latent bug this proposal also fixes — stops
  appearing for `archived` and `current`, since neither has a reopen transition; the phase chip renders
  `archived`/`current` distinctly from the three phases an operator is actively deciding about.

## Capabilities

### Modified Capabilities

- `spec-document-authority`: a document SHALL gain an `archived` phase reachable only from `approved`
  and only by the operator; `kind='capability'` SHALL be a document that starts and stays in a new
  `current` phase, outside the transition table, whose content only the operator can write; a
  document's `kind` SHALL be fixed at creation and a submission that disagrees with it SHALL be
  refused.

### Added Capabilities

- None. This is additive machinery within `spec-document-authority`'s existing domain (document phase,
  kind, and authority), not a new capability area.

## Impact

**Behaviour** — an approved change document can be archived by the operator; archiving does not touch
the document's tasks, requirements, digests or history, only its phase. A capability document is
created once (empty, at `current`) and thereafter written to only through a merge that names the
change document(s) it came from.

**API** — `POST /project/documents/phase?to=archived` works through the existing phase-transition
route with no new endpoint (the route is generic over `to_phase`; `transition()` gains the rule).
One new route, `POST /project/documents/{path}/merge`, operator-only, writes a capability document's
content and records the merge in the same call. The agent route `submit_spec_document` refuses when
the target document's `kind` is `capability`.

**Migration** — `0074`, a `batch_alter_table` recreate of `spec_documents` (the SQLite CHECK-constraint
trap: a table-level CHECK naming a column makes that column undroppable in place, so this is a
recreate in the shape of `0035`/`0058`/`0073`, not an ALTER), guarded for a missing table exactly as
those three are; plus a plain guarded `create_table` for `spec_document_merges`, no recreate needed
because it is new. Both migration head assertions (`hub/tests/test_migrations.py`,
`hub/tests/test_project_persistence.py`) move to `0074`.

**UI** — one new button, one bug fix to an existing one, one new phase-aware chip rendering. No new
page.

## Non-Goals

- **Not building a task-board scoping-by-document affordance.** That is N2b, contingent on N1's
  recommendation, coordinated against whichever of the two ships second (this one, first).
- **Not requiring a merge before a change can be archived.** N1 §3 is explicit that these are separate,
  possibly out-of-order acts — a change can sit merged-but-unarchived while evidence still accumulates,
  or (less commonly) be archived having produced no capability-document change at all. This proposal
  does not gate one on the other.
- **Not a general content editor for capability documents.** The only two ways a capability document's
  content changes are its empty scaffold at creation and a merge naming its source change(s). An
  operator wanting to hand-tweak prose with no change to cite is not served by this proposal; that is a
  materially different feature (a free-form editor bypassing the "cite what you merged" record) and is
  left for later if the operator asks for it.
- **Not an un-archive transition.** `archived` has an incoming transition from `approved` and none
  back. Reopening an archived change is not ruled out forever, but nothing in this session's evidence
  asks for it, and adding it now would be a guess at a workflow nobody has hit yet.
- **Not reorganising `openspec/`.** See N1 §2 and §6; this proposal is Hub-side data model only.
- **Not migrating `openspec/`'s existing 30 capability specs or 67 archived changes into the Hub.** This
  gives the *product* somewhere to put a current-behaviour corpus once it is used for real project work;
  it does not retroactively import openspec's own history, which CLAUDE.md's "Still prohibited" table
  continues to forbid moving wholesale.
