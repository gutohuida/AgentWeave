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
alongside valid output is a warning nobody sees. AgentWeave's own equivalent — the `diagnostics`
array on document state — has the same hazard if the UI renders the documents and not the
diagnostics.

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
