# Dogfooding findings — migrating the openspec corpus into AgentWeave

**Started:** 2026-08-20 · **Context:** the operator asked to move their development into AgentWeave.
The task is to migrate 33 openspec capabilities into `spec/` as a structured, indexed corpus.

This file is the running record CLAUDE.md asks for: *"The Hub-owned spec flow is simultaneously the
thing you are using and the thing you are building. When it frustrates you, that is a finding —
record it rather than working around it. That is the entire point of the migration."*

Each entry states **what happened**, **why it matters**, and **what would fix it**. Entries are
appended as they are hit, so the order is chronological, not by severity. Severity is called out in
the entry.

---

## 1. `spec/index.json` cannot be written at all — BLOCKING

**What happened.** The manifest is the only thing that gives a corpus a home, titles, parent/child
structure and ordering, and it is the part that *travels with the folder*. It cannot be produced.

Two independent causes:

**(a) Nothing in the product writes it.** Repo-wide, `index.json` appears three times and every one
is a read: `hub/hub/spec_manifest.py:105` (`load_manifest`), `src/agentweave/spec_manifest.py:147`
(the CLI twin), `hub/hub/spec_documents.py:38` (`INDEX_RELATIVE`, used by `read_index`).
`POST /spec/reindex` sounds like the writer but is not — it rebuilds the *requirement* index in the
database (`spec_index.reindex_project`), never the file manifest.

**(b) The vocabularies do not intersect.** `submit_spec_document` accepts
`kind ∈ {baseline, system-map, roadmap, change-spec, capability}`. `spec_manifest.VALID_KINDS` is
`{baseline, system-map, roadmap, change-spec}` — no `capability` — in **both** twins
(`hub/hub/spec_manifest.py:26`, `src/agentweave/spec_manifest.py:25`). And for `status`,
`spec_render.py:386` writes the lifecycle **phase** into `aw-spec-status`, while the manifest
expects a kind-derived constant (`living` for living kinds, `draft`/`approved` for change-spec).

The result for the three documents currently in `spec/`:

| document | head kind / status | valid manifest entry? |
|---|---|---|
| `spec/capabilities/project-instructions/spec.html` | `capability` / `current` | no — invalid kind **and** status |
| `spec/capabilities/quiet-hours/spec.html` | `capability` / `current` | no — invalid kind **and** status |
| `spec/changes/quiet-hours-for-agent-notifications/spec.html` | `change-spec` / `archived` | no — `archived ∉ {draft, approved}` |

Not one document can be described. And `load_manifest` returns `None` on any single violation, so
one bad entry invalidates the whole file and drops **every** document to `unindexed`.

**Why it matters.** This is the actual cause of the `home_ambiguous` diagnostic and the
`state: "unindexed"` that handoff 0061 left as an open question. That handoff reasoned that "files
+ `index.json` give the whole readable corpus anywhere". The files travel; the index cannot be
created, so the structure does not. Migrating 33 documents today would land 33 unindexed documents
with no home, no titles, no hierarchy and no ordering.

**Root cause is chronological, not conceptual.** `openspec/changes/archive/2026-07-29-add-spec-manifest/`
predates the capability and archived phases (migration `0074_archive_and_capability_phase.py`,
2026-08-16) by two and a half weeks. The manifest was never reconciled with the lifecycle that
shipped after it. Nothing about the design blocks the fix.

**Fix.** The `writable-spec-index` change: align the kind/status vocabulary with the shipped
lifecycle in both twins, and add the writer, wired into `POST /spec/reindex` — whose docstring
already claims its purpose is "a project whose documents predate the index".

---

## 2. There is no operator-side path to author document content

**What happened.** `submit_spec_document` refuses without a Hub-issued run credential:
`No bound run credential (AW_RUN_TOKEN is unset); the Hub must start this tool connection.` The
REST surface has `POST .../documents` to create an empty shell (`hub/hub/api/v1/spec.py:980`) and
routes for rigor, proposals, evidence and coverage — but **no route that writes a document's
content**. Content can only be authored by an agent the Hub spawned.

**Why it matters.** The identity binding is right and should stay: it is what makes authorship
attributable. But it means a corpus cannot be bootstrapped or bulk-imported by the operator at all.
Migrating 33 documents requires 33 agent runs. There is no import, no batch path, and no way for a
human to paste in a document they already have.

**What would be nice.** An operator-authenticated content-write route, or an explicit import that
takes a structured payload and attributes it to the operator rather than to an agent. The
`actor_kind` column already exists on `SpecDocumentEvent` and `SpecDocumentMerge`, so the data model
can express "the operator wrote this" — only the route is missing.

---

## 3. Document creation is one-way — there is no delete

**What happened.** No delete route exists for spec documents. `POST .../documents` creates; nothing
removes.

**Why it matters.** A migration of this size will produce mistakes — a wrong path, a wrong kind
(fixed at creation and unchangeable via `transition()`), a document created against the wrong
project. Every one is permanent. That makes the operator cautious in exactly the phase where they
should be free to experiment, which cuts against the stated organising constraint of ease of use.

**What would be nice.** Delete for a document that is still `exploring`, at minimum — the phase that
means "nobody is relying on this yet". `rename_spec_document` already refuses once approved, so the
precedent for phase-gated mutation is established.

---

## 4. The manifest asks for structure the database cannot supply

**What happened.** A manifest entry carries `path`, `title`, `kind`, `status`, `parent` and `order`.
`SpecDocument` (`hub/hub/db/models.py:1647`) carries `path`, `title`, `kind`, `phase` — and no
`parent` or `order`. `home` has no source either.

**Why it matters.** Any writer has to invent hierarchy and ordering, or leave them flat. For a
33-document corpus, flat is a real loss: the openspec corpus has natural grouping (agent-*,
spec-*, project-*) that would be thrown away on import.

**What would be nice.** `parent` and `order` as real columns, settable by the operator by dragging
in the UI. Until then the writer should derive a stable order and preserve any hand-set values it
finds rather than clobbering them.

---

## 5. `openspec new change` rejects this repo's own naming convention

**What happened.** `openspec new change "2026-08-20-writable-spec-index"` fails with
`Change name must start with a letter`. But every change in `openspec/changes/archive/` is
date-prefixed (`2026-08-20-portable-project-identity`, …), and CLAUDE.md documents the convention as
`openspec/changes/<date>-<name>/`.

**Why it matters.** Minor, but it means the documented convention and the tool disagree, and the
change created today (`writable-spec-index`) does not match its neighbours. Anyone sorting the
directory by name loses chronology.

**Note.** This is an openspec-tool constraint, not an AgentWeave one — recorded because AgentWeave's
own document naming should not repeat it. AgentWeave mints paths from a subject
(`rename_spec_document`), which avoids the problem entirely.

---

## 6. `openspec/config.yaml` had a typo that silently disabled two rules — FIXED

**What happened.** The rules block keyed spec rules under `spec:` where the schema expects `specs:`.
The CLI said so on every invocation — `Unknown artifact ID in rules: "spec". Valid IDs for schema
"spec-driven": design, proposal, specs, tasks` — on stderr, above the JSON, where it was never read.

**Why it matters.** Two rules had never once been applied to a spec artifact in this repo, including
*"Every requirement must be falsifiable — rewrite anything that cannot become a passing or failing
test."* That is a quality gate that has been silently off for the entire life of the corpus.

**Fixed** in this session. Worth carrying as a lesson rather than just a fix: a warning printed
alongside valid output is a warning nobody sees — it went to stderr, above well-formed JSON, on
every single invocation.

*Checked before asserting the obvious parallel:* AgentWeave does **not** have this problem in the
same place. `specNavigation.ts:200-208` separates `filed` documents from drifted ones and
`SpecCoverageBar` renders coverage diagnostics, so index state does reach the operator. The lesson
is about the openspec CLI's channel, not AgentWeave's.

---

## 7. `openspec/config.yaml` context contradicted CLAUDE.md — FIXED

**What happened.** The injected project context still read *"There is no `.agentweave/`,
`agentweave.yml`, or `spec/` here, and none should be created"* — the blanket prohibition CLAUDE.md
retired on 2026-08-16.

**Why it matters.** That text is prepended to every artifact an agent generates. Writing a
specification for migrating a corpus *into* `spec/` while being told `spec/` must not exist is a
direct contradiction, and the agent has no way to know which source wins.

**Fixed** in this session. The general lesson is the one that matters for AgentWeave: **there were
two places stating the project's standing instructions, and only one got updated.** AgentWeave has
exactly this shape today — project instructions in the DB, charters in the DB, and `CLAUDE.md` on
disk, all reaching an agent's context. Nothing reconciles them or notices when they disagree.

---

## 8. A corpus cannot be indexed until someone names a home — and no UI names one

**What happened.** Found while implementing the writer, not while designing it. `_select_home`
refuses to pick a home when several documents are candidates, on the stated grounds that a guess is
indistinguishable from an operator's decision. That is right. But the writer then has nothing valid
to write — `home` is a required manifest field — so a corpus of more than one document produces
**no index at all** until a home is named.

The 33-document migration hits this on document two.

**Why it matters.** The refusal is correct and the consequence is a dead end, because nothing in
the product lets the operator answer the question. `_select_home` emits `home_ambiguous`, which the
UI can display, but there is no control that sets a home and no field to store the answer in
outside the very file that cannot be written without it.

**Partly addressed.** `POST /spec/reindex` now takes an optional `home`, so the operator *can*
answer — via the API. That resolves the design's open question and unblocks the migration.

**What is still missing:** a way to answer it in the app. "Set as home" on a document in the spec
tree is the obvious shape, and it is the difference between a corpus that indexes itself and one
that needs a curl command. Recorded rather than built — it is a UI change, and this change was
already the deepest slice worth taking in one pass.

## 9. The manifest tests never used a document the product had actually rendered

**What happened.** Every existing test of `compute_intrinsic_conflicts` hand-wrote its HTML:

```python
'<meta name="aw-spec-kind" content="baseline">'
'<meta name="aw-spec-status" content="living">'
```

`living` is a value `spec_render` has never emitted. The test asserted "no conflict when content
matches" and passed — because it fabricated *both* sides of the comparison from the same wrong
vocabulary.

**Why it matters.** This is the mechanism by which finding 1 survived three weeks. The comparison
under test was exactly the one that was broken, and it was green throughout, because nothing in the
suite ever fed it output the renderer produced. A test that builds its own fixture from the same
misconception as the code cannot fail.

**What would be nice.** For a pipeline like this — payload → rendered HTML → parsed head → compared
against an index — at least one test should run the real renderer end to end rather than assert
against a handcrafted string. The new
`test_the_written_index_reports_no_metadata_conflict` does this for the index; the rendering path
would benefit from the same treatment.

## 10. `spec/index.json` is where the *only* copy of the operator's arrangement lives

**What happened.** Establishing what the writer must preserve made the exposure explicit: `parent`
and `order` exist **nowhere else**. They have no column (finding 4), so the file is not a cache of
database state — for those two fields it is the system of record.

**Why it matters.** It changes what a rebuild is allowed to do. A rebuild that recomputed `parent`
and `order` from the documents would not be "refreshing a derived artefact", it would be destroying
data with no other copy. The writer therefore reads the existing index before writing and carries
those two fields forward, and there is a test for it.

**What would be nice.** Either promote them to columns (so the file becomes a projection and a
rebuild is safe by construction), or state plainly in the schema that the file is authoritative for
arrangement. Right now it is authoritative by accident, which is the kind of thing that survives
until someone writes a well-meaning "just regenerate it" helper.

## 11. openspec's "must contain SHALL or MUST" check only reads the requirement's first line

**What happened.** A requirement whose normative sentence was on the *second* line of its block was
rejected with `must contain SHALL or MUST` — while the block plainly contained two `SHALL`s. Moving
the same sentence to the first line made it pass, with no other edit. Confirmed by doing exactly
that and re-validating.

**Why it matters.** The message names a condition that is visibly satisfied, so the natural
response is to distrust the validator or start adding redundant modals. The real rule is
positional and undocumented.

**Relevance to AgentWeave.** Its equivalent check — `submit_spec_document` refusing a requirement
with no `modal` — avoids this by making the modal a **separate field** rather than prose the
validator has to find. That is the better design, and it is worth stating explicitly as a reason to
keep it: a structured payload cannot have this class of bug, because there is nowhere else for the
modal to hide. One more argument for "you supply structure; the Hub renders the document".

---

## Findings outside the spec flow (recorded here so they are not lost)

- **`summaryForEvent` has no case for `project_adopted` or `agent_created`.** Both fall to the
  `default` branch, which probes `error`/`message`/`summary`/`title` — none of which these payloads
  carry — so the row renders its own event name twice and drops the detail. For adoption that means
  the operator never sees *which folder* was adopted or *under what id*.
  `hub/ui/src/lib/eventSummary.ts:11-12` already names this exact failure mode in a comment.
- **The browser suite's fixtures have decayed.** The three `taste-pass` jobs
  `hub/tests/browser/test_job_loop_block.py` asserts on by name exist in neither database, and its
  two fixture identities (`proj-5e960453`, `proj-b44fac0c`) no longer co-exist on any one Hub.
- **CLAUDE.md's trial-Hub table is stale.** It says this repo is registered on the 8010 Hub as
  `proj-5e960453`. The live 8010 instance serves `hub/data/agentweave.db`, which has no such row —
  only `proj-d0e4027e`, `proj-b44fac0c` and `proj-ff695d96`. There is therefore no dual-claim
  hazard, contrary to handoff 0061's next-step 2.
- **`agentweave-hub` is an editable install** pointing at `<repo>/hub`, so the port-8000 Hub runs
  this repo's working tree. Editing `hub/` and restarting it is a live-service concern, not a
  sandbox one.
