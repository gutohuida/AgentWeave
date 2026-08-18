# What archiving a spec means

## Why this document exists

Written for Q8 in the 2026-08-18 night run (`.claude/autonomous/STATE.json`). The operator asked
three questions, verbatim: *When we archive a spec, do we create a delta, or update the spec
directly? What does the structure/tree of a large spec look like? Is there a defined entry point
indicating where a delta gets applied?* This document answers all three with evidence from the code
and the live databases, names the viable ways forward with their costs, and **recommends nothing** —
the call is the operator's, per the queue item's own instruction.

**The premise driving this question has already moved, and CLAUDE.md does not yet say so.**
CLAUDE.md's Specifications section states: *"AgentWeave's lifecycle is `exploring → proposed →
approved` (`hub/hub/spec_lifecycle.py`) with no archive phase and no concept of a current-behaviour
specification. A document reaches `approved` and stops."* That was true when it was written. It is
not true of the code today. `hub/hub/spec_lifecycle.py:28-51` defines **five** phases —
`exploring`, `proposed`, `approved`, `archived`, `current` — and a change already shipped on master
that built exactly the machinery CLAUDE.md says does not exist:

- `git log --oneline master -- hub/hub/spec_lifecycle.py` shows `5e36209` — *"N2: implement the
  archive transition and the capability document kind"* — 2026-08-16, three days before this run.
- `openspec/changes/2026-08-16-the-corpus-keeps-what-shipped/` is the full proposal, design, and
  spec delta for it. It is not archived; it is still sitting in `openspec/changes/` unreconciled
  with CLAUDE.md's prose.
- The migration is `0074_archive_and_capability_phase.py`, and the current migration head is
  `0076` — two migrations past it. Nothing since has touched `spec_lifecycle.py`'s phase machinery.

So the honest framing is not "AgentWeave has nowhere to put shipped-capability truth." It has
somewhere. What it does not have is any real use of that somewhere: read on to §1, which is the
sharpest finding in this document. **This document does not propose fixing CLAUDE.md's prose** — a
previous run already logged that as `decisions_for_user.N3-claude-md-is-stale` in `STATE.json`, and
the fix belongs with whichever model the operator picks here, not before it.

## 0. What already exists, read from the code, not from memory

| Phase | Reachable from | Who can move a document there | What happens to content |
|---|---|---|---|
| `exploring` | document creation (default) | anyone (agent or operator) | freely rewritten |
| `proposed` | `exploring`, once closed | anyone, once `explore_closed_at` is set | freely rewritten |
| `approved` | `proposed` | **operator only** | refused (`document_approved`) — must reopen to edit |
| `archived` | `approved` **only** | **operator only** | untouched by archiving itself; the transition changes one column |
| `current` | nowhere — set once, at creation, for `kind='capability'` | N/A, not a transition target | refused for anyone but the operator, and only through the merge endpoint (§3) |

(`hub/hub/spec_lifecycle.py:38-51`, `TRANSITIONS`; `:221-249`, `transition()`'s guards.)

A **capability document** (`kind='capability'`) is a second, parallel kind of document, not a
special case of the four-phase one: it is created directly at `current`
(`spec_lifecycle.py:150`), never enters the explore/propose/approve machine at all, and its content
can be written only by the operator, only through the merge route (`spec_service.py:129-133`).
`kind` is fixed at document creation and a later submission that disagrees with it is refused
(`spec_service.py:123-127`) — a document cannot drift from `change-spec` to `capability` or back.

This is enforced at exactly one place each, the same discipline the module's own docstring states
for "an agent cannot approve": `spec_lifecycle.transition()` for archiving
(`spec_lifecycle.py:239-243`), `spec_service.save_document()` for capability writes
(`spec_service.py:129-133`). No MCP tool reaches either — `hub/hub/mcp_server.py` has no
`merge`/`archive` tool (grepped; zero matches), so an agent cannot even attempt either through the
one surface it can call. As of this run, no UI exists for the merge action either
(`SpecPhaseBar.tsx` has an "Archive" button per `92ea5d6`/`5e36209`, but no merge dialog) — the
route is reachable only by direct API call, which is how this document's own evidence below was
gathered.

## 1. Do we create a delta, or update the spec directly?

**Direct, whole-document update, cited but not computed — and this is the sharpest finding in this
document: the mechanism has shipped, is tested, and has never once been used for real.**

The merge endpoint, `POST /project/documents/{path:path}/merge`
(`hub/hub/api/v1/spec.py:1127-1191`), takes a **complete replacement payload** — the identical
`SpecPayload` shape (`hub/hub/spec_payload.py:145-169`) any ordinary document submits — plus a list
of `from_changes` paths it is citing as sources. It does not diff the change document against the
capability document, does not compute which requirements were added/modified/removed, and does not
migrate requirement identity automatically. `spec_service.merge_document()`
(`spec_service.py:550-599`) states this in its own docstring: *"by explicit authored merge"*, and
`proposal.md`'s own title for the change section makes the same point: *"An explicit authored
merge, not automatic requirement migration — the operator supplies the payload the capability
document ends up with."* The entry point records **that** a merge happened and **which** change
document(s) fed it (`spec_document_merges`, one row per source, `hub/hub/db/models.py` per
`design.md` D4) — not **what changed**, requirement by requirement. Reading a capability document's
history today tells you *when* it was folded and *from what*, not a line-level diff of what the
fold changed.

**Verified against the one real capability document this project has**, `proj-5e960453`'s
`spec/capabilities/quiet-hours/spec.html` (queried live from the database this session,
`hub/data/agentweave.db`):

```
spec_document_merges rows in this project:  0
```

The capability document exists, sits at `current`, and its stored payload has **zero requirements**
and an empty summary — an untouched scaffold. The change document it should eventually absorb,
`spec/changes/quiet-hours-for-agent-notifications/spec.html`, is `archived` with 7 real requirements
(`r1`-`r7`) ready to be cited. Nobody has run the merge. The mechanism was built, unit-tested
(`hub/tests/test_spec_merge.py`, 270 lines), and then never exercised against real content in this
repository — the "delta vs. direct" question has a code answer, but not yet a *lived* one. Nobody
has actually read what a merged capability document looks like, because none has ever been produced.

**A second, independent delta mechanism exists — for a completely different purpose, and the two
have never been reconciled.** `SpecEditProposal` (`hub/hub/db/models.py:1764-1820`,
`openspec/changes/2026-08-17-authoring-rigor-and-scope`, one day *after* the merge machinery
shipped) is a genuine per-requirement `add`/`modify`/`remove` delta: when a document's `rigor` is
`contract` or `gate`, a submission is diffed against stored content key-by-key
(`spec_service.py:259-289`, `propose_edit`) and lands as individually acceptable/rejectable
proposal rows instead of being applied directly. This is close to openspec's own
ADDED/MODIFIED/REMOVED shape (§2 has the exact comparison).

The catch: `merge_document()` calls `save_document()` (`spec_service.py:578`), and
`save_document()`'s branch to `propose_edit` is gated on `document.rigor`, not on `document.kind`
(`spec_service.py:148`). **A capability document's rigor is an ordinary, operator-settable field,
independent of its `kind` or `phase`.** Today the one real capability document in this project sits
at `rigor='sketch'` (queried live), so its merges apply directly. But nothing stops an operator from
raising a capability document — plausibly the *most* important documents to protect this way — to
`contract` or `gate` rigor. The moment that happens, the next merge onto it silently stops applying
directly and starts creating pending per-requirement proposals the operator must separately accept.
`test_spec_merge.py` has zero references to `rigor` (grepped) — this interaction is unbuilt-for and
untested, not merely undocumented. Whether that is the *right* behaviour (arguably yes — it is
exactly a delta review, for free) or an accident of two features shipping days apart without anyone
connecting them is exactly the kind of question this exploration exists to surface rather than
settle.

## 2. What does the structure/tree of a large spec look like?

**Within one document, both systems are already the same shape — flat.** `SpecPayload.requirements`
is `List[Requirement]` (`spec_payload.py:156`): no grouping, no sections, no sub-document. Openspec's
`### Requirement:` / `#### Scenario:` markdown convention is, read structurally, the identical
shape — a flat ordered list of requirement blocks inside one file. The largest real example in this
repository, `openspec/specs/task-lifecycle-governance/spec.md`, is 955 lines and 25 `### Requirement:`
headings (measured this session) — still one file, still a flat list, no internal tree. AgentWeave's
schema already matches this shape exactly; nothing about "a large spec" argues for restructuring the
single-document model.

**Across the corpus, the two systems structure differently, and neither has a real tree today.**

| | openspec | AgentWeave (Hub) |
|---|---|---|
| One capability's home | `openspec/specs/<capability>/spec.md` — one directory, by convention | `SpecDocument.path`, any string; `spec/capabilities/<name>/spec.html` is a convention **nobody enforces in code** — grepped `spec_naming.py`, zero hits tying a path prefix to `kind` |
| Change → capability link | Filename + prose only; a change's `specs/<capability>/spec.md` delta is applied to the matching capability folder by human/skill convention, never checked mechanically | `spec_document_merges` — a real foreign-keyed row, but only exists **after** a merge has actually happened (0 rows today, per §1) |
| Finding "what touched capability X" | Grep 67 archived change directory names for a slug that might not mention the capability at all (`openspec/explorations/2026-08-16-a-corpus-at-scale.md §2` — measured example: `2026-08-13-a-requirement-knows-its-work` is about `task-lifecycle-governance` and its name says nothing) | Query `spec_document_merges WHERE capability_document_id = ?` — exact, indexed (`ix_spec_document_merges_capability`) — **once merges exist to query** |
| Scale today | 30 capability dirs, 84 change dirs (17 open + 67 archived) — measured 2026-08-16 | 1 capability document, 1 archived change document, 0 merges — this project's real corpus is not at any scale yet |

So: openspec's structure is a real directory tree, discoverable by `ls`, enforced by nobody's code
— convention and skill discipline hold it together. AgentWeave's structure, once merges start
happening, would be a real relational graph, enforced by a foreign key and two indexes — but it is
querying an empty table right now, and the `spec/capabilities/` path convention that stands in for
"this is capability X's home" today is exactly as unenforced as openspec's folder convention is,
just with fewer documents to keep straight so far. Neither system has anything resembling a
*sub-document* tree for one large capability — a 955-line file is what "large" looks like in the
system being migrated from, and nothing in either system's evidence argues that flat stops working
before it gets much bigger than that.

## 3. Is there a defined entry point indicating where a delta gets applied?

**Yes, at the whole-document level: `POST /project/documents/{path:path}/merge`,
`hub/hub/api/v1/spec.py:1127`.** It is the *only* way a capability document's content ever changes
after its empty creation scaffold — enforced by the same operator-only refusal on every other
write path (`spec_service.py:129-133`), so there is no back door through the ordinary
`submit_spec_document` route either. Design D5 (`design.md:189-224`) lists its refusal order:
document must exist and be `kind='capability'` (409 `not_a_capability`); every named source must
exist and be `approved` or `archived` (409 `source_not_finished` — a merge cannot cite work still
being decided about); then the write goes through `save_document` exactly like any other content
write. That is a genuinely defined, single, operator-gated entry point — not diffuse, not
ambiguous, not reachable by accident.

**What it is *not* is fine-grained.** The "delta" a merge applies is the entire document, replaced
in one call — there is no route that says "apply just this one requirement's change to the
capability document." (§1's second finding is the qualification: if a capability document's `rigor`
is raised, the *effective* granularity becomes per-requirement via `spec_edit_proposals` — but that
is an accident of a shared code path, not a designed entry point for capability merges
specifically; nothing in `design.md` or `test_spec_merge.py` names it.) If "entry point" means "the
one place in the code the operator invokes to fold a change in," §3's answer is unambiguous: yes,
one route, well-refused, well-tested. If it means "the one place a specific requirement's delta
gets pinpointed and applied," no such thing exists yet at any granularity finer than the whole
document.

## Viable models forward — costs, rejections, recommending none

**Model A — Adopt what already shipped.** Ship the merge UI (D7 in `design.md` scoped it out
deliberately; the route has existed with no dialog since 2026-08-16), and start actually running
merges — beginning with the one sitting ready right now, `quiet-hours-for-agent-notifications` into
`spec/capabilities/quiet-hours/spec.html`.
- *Cost*: low. The mechanism, its tests, and its data model are already built and merged to master;
  the only missing piece is a UI dialog wrapping an endpoint that already works.
- *Rejection reason*: zero real evidence it produces something worth reading at scale — the
  mechanism has never been exercised even once, so "is a whole-document authored merge actually
  pleasant to maintain as a capability document grows past a handful of requirements" is untested
  by anything but design reasoning. Running it for real, even manually via the API before any UI
  exists, would answer that cheaply — and would also settle whether the `rigor`/`propose_edit`
  interaction from §1 is a feature or a bug, since it can only be observed by actually raising a
  capability document's rigor and merging into it.

**Model B — Route capability merges through the existing per-requirement delta, deliberately.**
`spec_edit_proposals` (§1) already computes exactly the ADDED/MODIFIED/REMOVED shape openspec uses,
already exists in the schema, and — per §1 — is *already reachable* by a capability document whose
rigor is `contract`/`gate`. This model does not build a new delta representation; it decides that
capability documents should default to (or be required to hold) `contract`/`gate` rigor, so every
merge is reviewed requirement-by-requirement rather than applied as one opaque replacement.
- *Cost*: small if scoped exactly this way (a rigor default/requirement, plus closing the gap §1
  found — proposal review UI for a capability document, tests for the merge-at-gated-rigor path).
  Large if it grows into "give capability merges their own bespoke delta schema" — `design.md` D2
  already corrected away from that once, having read `spec_payload.py` directly and found no delta
  shape anywhere in the Hub's JSON payload convention; reopening that specific decision needs a
  reason `design.md` didn't already have, not just "openspec's files look like this."
- *Rejection reason*: no operator has asked for per-requirement review of a capability merge yet,
  and it adds friction (an accept/reject step per requirement) to an act — folding in a finished,
  already-approved change — that Model A treats as a single confident write. Whether that friction
  is warranted is exactly the kind of judgment call that benefits from Model A's cheap real-world
  trial first.

**Model C — Build real capability-level structure (a tree).** Give `kind='capability'` an actual
grouping construct — a capability as an aggregate of multiple documents/sections, with the
`spec/capabilities/<name>/` path prefix enforced in code instead of assumed by convention (closing
the gap §2 found).
- *Cost*: real, and structural — touches document discovery (`spec_documents.py`), the navigation
  tree (`specNavigation.ts`), the path-minting convention (`spec_naming.py`), and every place that
  currently assumes one path names one document.
- *Rejection reason*: §2's evidence says this problem doesn't exist yet in either system — openspec's
  own largest real capability spec is one 955-line file, not a tree, at 30 capabilities and 84
  changes. Building tree structure now would be solving a scaling problem neither corpus has hit,
  in the system being migrated *to*, before the system being migrated *from* has hit it either.

None of these are mutually exclusive on a difficulty axis — A is a prerequisite for observing
whether B or C are ever actually needed, since the honest answer to all three of the operator's
questions right now is "the code has an answer; reality has not tested it."

## What Q10 (the AgentWeave-native spec translation) needs from whichever model wins

Whatever the operator decides, Q10's translation work needs three concrete things settled first,
not guessed at mid-translation:

1. **Whether a translated capability document is created empty-then-merged (as designed) or seeded
   directly with content**, the way `hub/seed_taste_doc.py` created the change-spec document in
   this project — by calling `spec_lifecycle.create_document` then `spec_service.save_document`
   directly, bypassing the merge route entirely because there was no finished change document yet
   to cite. A first translation of an openspec capability spec has the same shape: there is no
   AgentWeave change document to cite as a source, because the capability was never "approved"
   inside AgentWeave — it was approved inside openspec, which AgentWeave's data model cannot see.
   Model A's merge route, as built, **requires** at least one `from_changes` source in `approved`
   or `archived` phase (`design.md` D5 step 4) — so a first-generation openspec-to-AgentWeave
   translation cannot go through the merge endpoint at all without first fabricating a synthetic
   change document to cite, which would be recording a fiction. This needs a decision before Q10
   writes a single document, not discovered by Q10 hitting a 409.
2. **Whether translated documents start at `rigor='sketch'` or something higher** — §1's finding
   means this single field decides whether every future merge into a translated capability document
   applies directly or requires per-requirement review, and it is exactly the kind of choice that
   is expensive to change after 30 capabilities have already been translated one way.
3. **How the `spec/capabilities/<name>/` path convention is decided**, since §2 found it enforced
   nowhere — Q10 translating 30 capabilities by hand will either establish that convention
   accidentally (30 documents landing wherever the translating agent's judgment puts them, no two
   guaranteed consistent) or deliberately, if this exploration's finding is read before Q10 starts.

## Not decided here

Restating the operator's three questions, answered but not settled: (1) direct whole-document
update, cited not computed, is what's built — a parallel per-requirement delta mechanism exists but
was built for a different purpose and has an untested, possibly-accidental connection to capability
merges; (2) no tree exists in either system at the single-document level, and none is evidenced as
needed yet at the corpus level either; (3) yes, one defined, well-refused entry point exists, at
whole-document granularity only. Which model to build toward — adopt as-is, lean into the
already-half-built delta path, or build real corpus structure — is the operator's call. This
document recommends none of them.
