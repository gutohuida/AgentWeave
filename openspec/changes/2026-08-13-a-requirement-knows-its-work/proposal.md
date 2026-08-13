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
- **Evidence, with an actor.** `requirement_evidence` records kind, a bounded locator or payload,
  the producing actor and run, and the digest it was produced against. `evidence_reviews` is
  append-only acceptance/rejection with operator attribution. **An agent assertion is never
  evidence** — that rule is the reason this table exists rather than a boolean on the task.
- **Deterministic coverage state**, one query, one precedence, so a requirement badge and a project
  total cannot disagree: `drifting` → `stale` → `evidence_awaiting_review` → `verified` →
  `in_progress` → `not_started` → `unserved`.
- **Drift as a diagnostic, never an edit.** When evidence is recorded, capture the implementation
  footprint. A later change to a linked footprint without a new requirement revision raises a
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

## Open questions for review

Carried from the design source, plus one this run added. Each needs a decision before the phase that
consumes it.

1. **Bounded evidence formats and retention** — locator versus payload, and limits, "without turning
   the database into an artifact store."
2. **Non-git implementation footprints** — required here, or after the git-backed path, with an
   explicit `unavailable` state?
3. **Does a footprint on an unmerged agent branch count as evidence?** New. The design assumes work
   lands somewhere a commit can be named; today it does not. Answering "no" makes evidence
   unobtainable until F4 is solved; answering "yes" means evidence can name a commit that never
   reaches the product.
4. **Evidence policy per document, or accepted-evidence-by-default for contracts?** Gates
   necessarily require accepted evidence. This one mostly belongs to B4 and is listed so it is not
   lost.
