# Design — A requirement knows its work

Technical source: `openspec/explorations/2026-08-03-specification-authority-technical.md`
(Child 2). This freezes what that document left illustrative and records the decisions it left open,
plus what the 2026-08-13 end-to-end run changed about them.

## D1. The index is derived; the document stays authoritative

`spec_requirements` is rebuilt from the document on every save. It never holds wording that is not
also in the file, and dropping the table must cost nothing but a reindex.

**Why not make it authoritative.** The operator decided on 2026-08-10 that the HTML is the
specification. A row that could disagree with the file would create a second source of truth, and
the failure would be silent — the badge saying one thing, the document another. `save_document`
already writes the file and the digests in one function for exactly this reason.

**Columns** (project-scoped unique on `(project_id, identifier)`):

| column | why |
|---|---|
| `id`, `project_id`, `document_id` | identity and ownership |
| `identifier` (`FR-n`) | the stable handle everything else points at |
| `key` | the agent's document-scoped handle; needed to re-resolve after a rewording |
| `state` (`active` \| `retired`) | a retired requirement keeps its links and evidence |
| `digest` | current semantic digest — the thing evidence is pinned against |
| `anchor` | where it lives in the rendered document |
| `observed_at` | when the index last agreed with the file |

`spec_requirement_revisions` is append-only: old digest, new digest, source (`hub` \| `external`),
classification, actor, time. This is what makes "the meaning moved" a fact rather than an inference.

## D2. Links are rows, and they outlive the task

`task_requirement_links`: project, task, requirement, creating actor and run, created time. Real
foreign keys, project-scoped.

**Links are not deleted when a task reaches a terminal state.** The question this whole change
exists to answer — *what work served this requirement?* — is asked mostly about finished work.
Deleting on completion would erase the answer at the moment it becomes interesting.

**Why not keep the JSON.** `Task.requirements` holds `"FR-8 — initialize-members"`: a string that
looks like a reference and resolves to nothing. It cannot be joined, cannot be checked, and does not
notice when `FR-8` is retired or reworded. Every question in the proposal's list is a join away with
rows and unanswerable without them.

## D3. The migration keeps what it cannot understand

Per the design source: *"preserve recognizable legacy values as unresolved references until
explicitly mapped; do not drop opaque values silently."*

Observed legacy shape, from the live run: `["FR-8 — initialize-members", "FR-1 — local-single-ledger"]`
— an identifier and a key, em-dash separated. That is a convention the agent happened to follow, not
a guarantee, so the migration:

1. parses a leading `FR-\d+` where present and, **only if that identifier resolves in the same
   project**, writes a real link;
2. otherwise writes an `unresolved_reference` row preserving the original string verbatim;
3. never discards a value, and never invents a requirement to match one.

`Task.requirements` is kept as a nullable column through this change and read by nothing, so a
mis-parse can be re-derived rather than reconstructed from a backup. Its removal belongs to a later
change once the unresolved set is empty.

## D4. Evidence has an actor, and an agent's word is not evidence

`requirement_evidence`: requirement, **the digest it was produced against**, kind, bounded locator
or payload, producing actor, producing run where applicable, produced time, review state.

Kinds: `test_result`, `review_record`, `artifact_diff`, `manual_observation`, `external_reference`.

**Pinning to the digest, not the requirement, is the whole mechanism.** Evidence accepted against
one wording says nothing about a different wording, and the difference is exactly what
`requirement_digests` was recorded to expose and what nothing has ever read.

**An agent assertion is never evidence.** A run reporting "tests pass" produces a `test_result`
whose locator names the artifact, and it enters `review_state = awaiting`. This is not distrust of
models specifically — the end-to-end run produced an honest agent that said *"this should be treated
as unverified-by-execution"*, and a less careful one would have said "tests pass" with the same
authority. The record must be able to tell those apart, and only an authenticated actor plus an
artifact can.

`evidence_reviews` is append-only: decision, operator attribution, time, reason. No update, no
delete — the same shape as `TaskTransition`, and for the same reason.

## D5. One query, one precedence

Coverage state is computed by a single function, and the document badge, the project total and
(later) B4's gate all call it. Two implementations would disagree eventually, and the disagreement
would be invisible until someone compared two screens.

Precedence, highest first — taken from the design source unchanged:

1. `drifting` — an unresolved drift record exists
2. `stale` — evidence exists but none applies to the current digest
3. `evidence_awaiting_review` — current-digest evidence exists, review pending
4. `verified` — sufficient accepted current-digest evidence
5. `in_progress` — linked work active, or completed without evidence
6. `not_started` — linked work exists, not started
7. `unserved` — no work linked

`unserved` is the state the end-to-end run needed and could not express: nine requirements, six
tasks, and no way to ask whether every requirement had somewhere to be built.

Structurally invalid or unidentified requirements are **diagnostics outside coverage**, not a
coverage state. They are not "unserved"; they are broken, and a gate must refuse on them separately.

## D6. Drift is a candidate, never an edit

When evidence is recorded, capture an implementation footprint: git commit plus changed path/blob
ids where the workspace is a repository; bounded paths and content hashes otherwise; test
identifiers where applicable.

A later change to a linked footprint, with no new requirement revision and no explicit resolution,
raises a **drift candidate**. The operator resolves it as *specification updated*, *implementation
corrected*, or *no specification change required*; the resolution records the current digest and
fingerprint so the same change is not reported twice.

**Nothing here edits a document.** "The implementation changed" is observable. "The requirement
should have changed" is a judgement, and a system that inferred it would rewrite an approved
specification on the strength of a file diff.

**Open, and load-bearing:** the end-to-end run found that approved work never leaves
`agentweave/<agent>` — commits are `Auto-snapshot: builder's turn` and `master` keeps only a README.
So a git footprint today names a commit on a branch nothing merges. Either evidence may name it
(and "verified" can describe code that never ships), or it may not (and nothing is verifiable until
integration exists). **This is question 3 in the proposal and needs an answer before the evidence
phase, not before the link phase** — which is why the tasks are ordered as they are.

## D7. Agent actions are run-bound

An agent recording evidence does so through its run credential, and the run is stored on the
evidence. Identity is never taken from a request body — the same rule `submit_spec_document` already
follows. An agent has no route that accepts or rejects evidence, for the same reason it has no route
that approves a document.

## D8. What is deliberately deferred

- **The gate** (B4). This change supplies the query; refusing a transition is B4's, and it lands in
  B1's transition service so no route can bypass it by assigning `Task.status` directly.
- **The task board's traceability surfaces.** Program C is split on purpose: how the board looks is
  Program A, what it knows is this change. Designing the surface before the fields exist would be
  guessing — the roadmap says so explicitly.
- **Requirement injection into a build turn.** This makes it possible and cheap (~286 tokens for a
  three-requirement task, invariant to product size). Doing it is a separate change, because *which*
  turns receive it and how it is phrased is a context-design question, not a data one.
