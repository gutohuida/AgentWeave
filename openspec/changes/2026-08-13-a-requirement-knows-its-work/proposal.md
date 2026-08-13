# A requirement knows its work

Roadmap **B3** — *traceability, evidence, and drift*. Technical design source:
`openspec/explorations/2026-08-03-specification-authority-technical.md`, Child 2. Evidence that it
is needed now: `openspec/explorations/2026-08-13-explore-to-development-end-to-end.md`.

## Why

**The approved specification stops mattering the moment building starts.**

Driving the loop end to end on 2026-08-13 produced a working product — six approved tasks, 99
passing tests — and at no point could anything answer the question the whole program exists to
answer: *did we build what we agreed?*

What is actually stored today, from that run:

```json
["FR-8 — initialize-members", "FR-1 — local-single-ledger"]
```

That is `Task.requirements`: **free text in a JSON column**. It reads like a link and is not one.
Nothing resolves `FR-8` to a requirement, so nothing can answer any of:

- which approved requirements have no task?
- which requirement changed *after* the task serving it was approved?
- what evidence exists that FR-11 works, and who accepted it?
- if I reword FR-9, what work is now suspect?

Three things already in the codebase were built for these answers and are consumed by nothing:

- **`SpecDocument.requirement_digests`** is computed on every save. Its own docstring says
  *"Nothing here consumes these."* It exists so a later change can tell that a requirement's meaning
  moved out from under evidence accepted against the old wording — which is undetectable after the
  fact if the digests were never taken.
- **`aw_identity`** mints stable `FR-n` identifiers and retires them. Verified stable across a
  reopen-and-extend cycle in the same run.
- **`gate_policy: {"rigor": ...}`** round-trips through save and render with **zero** consumers.
  That one belongs to B4 and is named here only so nobody rebuilds it.

Meanwhile the document's own evidence section, after the product was built and its tests passed,
still read:

> *"No implementation exists to validate against the specified behaviors."*
> *"All acceptance criteria describe proposed coverage, not passing tests."*

**The specification cannot tell whether it describes a plan or a shipped thing.**

And the cost is not only bookkeeping. The builder in that run could not read the specification at
all — `spec/` is untracked, so it is absent from every agent worktree — and worked from the task's
copied text instead. A real link is what makes the alternative cheap: injecting the requirements a
task is *bound to* costs ~286 tokens and does not grow with the product, where injecting the whole
document costs ~1,500 and does.

## What Changes

- **A derived requirement index.** `spec_requirements` rows carry stable identifier, document,
  active/retired state, current semantic digest and anchor. Derived from the document on every save;
  **these rows never author wording** and can be rebuilt from the files.
- **Task↔requirement links replace `Task.requirements`.** A normalized `task_requirement_links`
  table with real foreign keys. Links survive a task reaching a terminal state — the record of what
  work served a requirement is the point.
- **A migration that does not lie.** Recognizable legacy values are preserved as **unresolved
  references** until explicitly mapped; opaque values are kept, never silently dropped.
- **Evidence is files; the database holds the pointer.** Evidence is whatever demonstrates the work
  — a test run, a screenshot, a diff, a path. It is gathered into a folder tree inside the project,
  and `requirement_evidence` records the kind, the locator, the producing actor and run, and the
  digest it was produced against. **Retention is a project policy** — on acceptance, daily, monthly,
  manual, or never — so an operator who wants to manage the tree themselves simply chooses never.
  This is the same shape the product already uses for specification documents: the file is the
  thing, the row is derived.
- **A tester agent accepts evidence; without one, the operator does.** An operator grants
  `can_accept_evidence` to an agent, the way `can_recall` and `can_read_checkpoints` are already
  granted. That agent may not accept evidence it produced itself — the same author/reviewer rule
  `task-lifecycle-governance` already enforces for approval, applied one level down. A project with
  no such agent defers every acceptance to the operator, which is a supported way to work rather
  than a degraded one.
- **An agent assertion is still never evidence.** A stored artifact is a fact; a run's claim about
  what it proves is not. That is why acceptance is a separate, attributed act on a separate record.
- **Deterministic coverage state**, one query, one precedence, so a requirement badge and a project
  total cannot disagree: `drifting` → `stale` → `evidence_awaiting_review` → `verified` →
  `in_progress` → `not_started` → `unserved`.
- **Coverage also reports whether the evidence is integrated**, and no surface may show the state
  without it. Approved work in this product does not leave `agentweave/<agent>` today, so evidence
  can name a commit that never reaches the main branch. Reporting `verified` alone would be true of
  code that does not ship; **`verified, not integrated`** is the honest answer and makes the missing
  integration step visible in the product rather than only to someone driving the loop by hand.
- **Drift as a diagnostic, never an edit.** When evidence is recorded, capture the implementation
  footprint — commit and changed blob ids in a git project, **and file paths with content hashes
  where there is no repository**, because non-git projects are a supported first-class case and
  shipping without that path would leave a whole class of project unverifiable. A later change to a linked footprint without a new requirement revision raises a
  *candidate* the operator resolves as *specification updated*, *implementation corrected*, or *no
  change required*. **"Implementation changed" is detectable; "the requirement should have changed"
  is not** — so nothing here ever edits a document.
- **Navigation both ways**, and project coverage, over the same query the states come from.

## Capabilities

### Added Capabilities

- `requirement-traceability`: a requirement SHALL know which work serves it, what evidence exists
  for it, and whether that evidence still applies to its current meaning.

## Impact

**Behaviour** — the specification becomes answerable. "Which requirements are unserved?" and "what
changed under this evidence?" become queries rather than a reading exercise.

**Schema** — five new tables and one migration off `Task.requirements`. The design's persistence
model is followed; exact columns are frozen in `design.md`.

**API/UI** — coverage on the document and the project; requirement ↔ task navigation. The task
board's traceability surfaces are Program A's job and are explicitly *not* designed here, per the
roadmap's split of Program C.

**This unblocks** injecting the right requirements into a build turn (F1) and lets a document learn
it was implemented (F5). Neither is delivered here; both become possible.

## Non-Goals

- **Not the completion gate.** Refusing a transition on unverified requirements is B4, and the
  design puts it in B1's transition service. This change supplies the query it will ask.
- **Not rigor promotion/demotion.** `gate_policy` stays an inert passthrough until B4.
- **Not the authoring workspace or in-document proposals.** B5.
- **Not deciding how work is integrated.** The end-to-end run found that nothing merges an approved
  task's code — it stays on `agentweave/builder` under `Auto-snapshot` commits. That hole is real
  and unowned by any roadmap entry, and it bears directly on what a footprint *means*. Called out in
  design D6 as a question for review rather than answered here.
- **Not making the index authoritative.** The HTML document remains the authority (operator
  decision, 2026-08-10). Every table here is derived or a workflow record, and reindexing must be
  able to reconstruct current document state.

## Decisions taken at review

All four questions the design source left open are answered. None remains blocking.

1. **Evidence is anything that demonstrates the work**, gathered as files in a project folder tree,
   with the database holding kind, locator and attribution. **Retention is a project policy** — on
   acceptance, daily, monthly, manual, or never. This avoids the design's stated fear of "turning
   the database into an artifact store" by not making it one: the filesystem stores, the row points.
2. **Both footprint paths ship together.** Git projects record commit and changed blob ids; projects
   without a repository record file paths and content hashes. Non-git projects are a supported
   first-class case (`2026-08-12-run-without-a-git-repository`), and a git-only first cut would leave
   them permanently unverifiable.
3. **Evidence may name a commit on an agent branch, and coverage reports separately whether that
   commit is integrated.** Refusing unintegrated footprints would make nothing verifiable until an
   integration step exists; accepting them silently would let `verified` describe code that never
   ships. Reporting both is the only answer that is neither blocking nor untrue, and it surfaces the
   missing integration step in the product.
4. **A tester agent accepts evidence; a project without one defers to the operator.** Acceptance is
   an operator-granted per-agent capability, not a role and not something a charter confers — a
   charter describes how an agent behaves, and authority must come from the operator. An agent may
   not accept evidence it produced, which is the rule `task-lifecycle-governance` already applies to
   task approval. Working with no tester agent at all is a supported choice; the operator becomes
   the acceptor and knowingly takes the bottleneck.

**Deferred to B4, deliberately:** whether a `contract`-rigor document requires accepted evidence or
merely recorded evidence. `gate` necessarily requires acceptance, or the gate certifies itself.

## Later, and out of scope here

**Narrowing what a command may do** — the workspace posture checks literal absolute paths and is a
boundary rather than a sandbox, so a command naming no absolute path is allowed, including network
access and package installation. The operator's direction is that this is hook-shaped work, and
hooks are not implemented. `openspec/explorations/2026-08-10-enforcing-the-development-cycle.md`
already sets the rule that should govern it when they are: **no capability may exist only in a
hook** — a hook may make an independently-enforced rule fire sooner or more pleasantly, and removing
it must leave the same rule firing at the boundary. Making hooks easy to create from the Hub is
noted as wanted and low priority.
