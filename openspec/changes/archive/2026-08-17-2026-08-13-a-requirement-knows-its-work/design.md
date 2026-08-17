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

## D4. Evidence is a file; the row points at it

`requirement_evidence`: requirement, **the digest it was produced against**, kind, locator, producing
actor, producing run where applicable, produced time, review state.

Kinds: `test_result`, `screenshot`, `artifact_diff`, `review_record`, `manual_observation`,
`external_reference`. The list is open at the edges on purpose — evidence is whatever demonstrates
the work, and constraining it to what was imaginable today is how a format becomes a cage.

**The artifact lives in the project, not the database.** Evidence is gathered under a folder tree in
the project directory; the row records where. The design source worried about "turning the database
into an artifact store", and the answer is simply not to: this is the same division the product
already uses for specification documents, where the file is authoritative and the row is derived.
It also means an operator can open, diff, move and archive evidence with ordinary tools.

**Retention is a project policy**, not a hard-coded rule: on acceptance, daily, monthly, manual, or
never. `never` is a first-class choice — an operator who wants to manage the tree themselves should
not have to fight a cleaner. Whatever the policy, deleting an artifact SHALL NOT delete the
`requirement_evidence` row: that a thing was verified, by whom, and against which digest is the
record; the artifact is the attachment. A row whose artifact is gone reports as such rather than
vanishing.

**Pinning to the digest, not the requirement, is the whole mechanism.** Evidence accepted against one
wording says nothing about a different wording, and that difference is exactly what
`requirement_digests` was recorded to expose and what nothing has ever read.

## D4a. Who accepts evidence

**An agent the operator has granted `can_accept_evidence`, or the operator.**

An agent's assertion is still not evidence. But that rule was aimed at the wrong half: a stored test
artifact is a *fact*, and it is the claim about what it proves that needs judging. So the artifact
may be produced by anyone; the **acceptance** is the controlled act.

`can_accept_evidence` is an operator-granted per-agent capability, alongside `can_recall` and
`can_read_checkpoints` which already work this way. Deliberately **not** a role (the role subsystem
was deleted and must not return) and deliberately **not** conferred by a charter — a charter says how
an agent behaves, and behaviour is not authority. The "Verifier" charter may well describe such an
agent; it does not grant it anything.

**An agent may not accept evidence it produced.** `task-lifecycle-governance` already refuses a
transition to `approved` requested by the agent that recorded the completion, on agent identity
rather than run identity, because "a different run" is satisfied by an agent continuing its own work.
The same rule and the same reasoning apply here.

**A project with no such agent defers every acceptance to the operator**, and that is a supported way
to work rather than a degraded one — the operator knowingly takes the bottleneck. Exactly as
`task-lifecycle-governance` permits the operator to approve regardless of who produced the work,
"a single-operator project would otherwise be unable to approve anything."

`evidence_reviews` is append-only: decision, actor (operator or the accepting agent), run where an
agent acted, time, reason. No update, no delete — the same shape as `TaskTransition`, for the same
reason.

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

**Coverage is a state *and* an integration answer, and no surface may show one without the other.**
Reachability of the evidence's footprint from the project's main branch is reported alongside the
state, so `verified` never appears alone for work sitting on an agent branch. It is not an eighth
precedence level: the precedence ranks *evidence quality*, and integration is an orthogonal fact
about the same evidence. Ranking them together would force a choice between "stale but merged" and
"verified but not merged" that has no correct answer.

`unserved` is the state the end-to-end run needed and could not express: nine requirements, six
tasks, and no way to ask whether every requirement had somewhere to be built.

Structurally invalid or unidentified requirements are **diagnostics outside coverage**, not a
coverage state. They are not "unserved"; they are broken, and a gate must refuse on them separately.

## D6. Drift is a candidate, never an edit

When evidence is recorded, capture an implementation footprint. **Both paths ship together:**

| workspace | footprint |
|---|---|
| a git repository | commit sha, plus the blob ids of the changed paths |
| no repository | the changed paths, plus a content hash of each at that moment |

Non-git projects are a supported first-class case (`2026-08-12-run-without-a-git-repository`), and a
git-only first cut would leave every one of them permanently unverifiable. Test identifiers are
recorded where applicable in both.

A later change to a linked footprint, with no new requirement revision and no explicit resolution,
raises a **drift candidate**. The operator resolves it as *specification updated*, *implementation
corrected*, or *no specification change required*; the resolution records the current digest and
fingerprint so the same change is not reported twice.

**Nothing here edits a document.** "The implementation changed" is observable. "The requirement
should have changed" is a judgement, and a system that inferred it would rewrite an approved
specification on the strength of a file diff.

**Resolved: evidence may name a commit on an agent branch, and coverage says whether it is
integrated.** The end-to-end run found that approved work never leaves `agentweave/<agent>` —
commits are `Auto-snapshot: builder's turn` and `master` keeps only a README. So a git footprint
today names a commit on a branch nothing merges.

Refusing such a footprint would make nothing verifiable at all until an integration step exists, and
B3 would ship a coverage system permanently answering "not verified". Accepting it silently would
let `verified` describe code that never ships. So: record it, and report **reachability from the
project's main branch as a separate attribute of coverage** that no surface may omit (D5). The
honest state is `verified, not integrated`, and it makes the missing integration step visible in the
product instead of only to someone driving the loop by hand.

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
