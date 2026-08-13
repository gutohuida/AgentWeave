# Approved means it is in the product

Closes **F4** — *nothing integrates the work* — from
`openspec/explorations/2026-08-13-explore-to-development-end-to-end.md`. Picks up the question B4
explicitly left on the floor:

> *"**Not gating on integration.** B3 reports `verified, not integrated`; whether that should refuse
> approval is a real question and belongs with whoever owns the integration step, which nothing
> currently does."*

This change is what owns it.

## Why

From the 2026-08-13 end-to-end run:

> `master` contains `README.md`. Every line of the product lives on `agentweave/builder`, in commits
> titled "Auto-snapshot: builder's turn" — no task id, no requirement id. Six approved tasks and 99
> passing tests, and none of it is on the main branch.

**"Approved" did not mean "in the product", and no step in the lifecycle said so.**

B3 made this visible without fixing it. `EvidenceFootprint`'s own docstring states the problem:

> *"`reachable_from_main` is what stops `verified` describing code that never ships. Approved work in
> this product currently stays on a per-agent branch that nothing merges, so a footprint routinely
> names a commit the product does not contain."*

So the Hub can already tell you the work is stranded. It can already tell you (`_merge_tree_conflicts`)
whether merging it would conflict. It has per-agent worktrees, per-agent branches, and snapshot
commits. **F4 is not missing infrastructure. It is missing a decision point and the act that follows
it.**

## What Changes

- **Approval merges.** The transition into `approved` merges the approved work into the project's
  main branch. Approval is what puts the work in the product; that is what the word will mean.
- **The merge is local and never pushes.** No remote, no credentials, no branch-protection risk,
  nothing that can damage a shared branch. The operator pushes.
- **The project's main branch becomes explicit configuration.** `MAIN_BRANCH_NAMES = ("main",
  "master")` is a guess tried in order. That is correct for a read-only report — the worst case is
  `unknown`, which is why it was written that way — and unsafe for an automatic merge. A guessed
  target is how you write to the wrong place. The guess is demoted to a *suggestion* offered at
  project setup.
- **Mergeability joins the gate.** A branch that conflicts with main is refused *before* approval, in
  the same typed refusal that already says "FR-14 has no evidence" — not discovered halfway through
  a merge.
- **Every integration is recorded**: what was merged, into what, on whose approval, and what
  happened. Append-only.

## What does not change

**The gate stays on `approved`, and the transition graph is untouched.** B4 §3.2's reasoning still
holds exactly as written — evidence is accepted after review and review follows completion, so
refusing `completed` would deadlock the path. Evidence acceptance is not a task transition; it
already sits where it needs to. This change adds a *side effect* and one *precondition* to an edge
that already exists. Nothing about B4 is being restructured.

**Merging happens regardless of rigor.** Rigor governs *who can get a task to `approved`*;
integration is what `approved` **means**. If turning rigor off also silently stopped merging, an
operator lowering a gate to get unblocked would quietly also stop shipping, and nothing would have
told them.

## What gets merged

**The commit the accepted evidence names, not the agent's branch.**

Agent branches are per *agent* (`branch_name(agent)` → `agentweave/<agent>`), not per task. One
builder's branch carries every task it has ever worked on, so merging the branch on approval of one
task would ship every unapproved thing beside it.

B3 already records the answer: each piece of accepted evidence carries an `EvidenceFootprint` with
`commit_sha`. Merging *that commit* brings in the work up to and including it, and leaves everything
committed after it behind.

**The consequence, stated plainly:** merging a commit also merges everything it descends from,
including earlier work on the same branch that may not itself be approved. That is a property of
agents sharing one branch, not of this change — the commit graph already says those commits are
dependencies. Per-task branches would remove it and are a **separate, larger change** (see
Non-Goals).

## Capabilities

### Modified Capabilities

- `task-lifecycle-governance`: approval SHALL integrate the approved work into the project's main
  line, SHALL be refused when that work cannot be merged cleanly, and SHALL record what it did.
- `local-project-workspace`: a project SHALL carry an explicit main branch, and the Hub SHALL NOT
  merge into a branch it inferred.

## Impact

**Behaviour** — the demonstrable outcome: *a task approved with accepted evidence has its work on
the main branch when the transition returns, and coverage reports the requirement `integrated`
rather than `verified, not integrated`.* Today that second answer is the only one reachable.

**Schema** — `Project.main_branch`; a `task_integrations` record. Migration `0070`.

**Risk** — this change makes the Hub write to the operator's git history automatically. Three things
bound it: it never pushes, it never merges into a branch nobody named, and it refuses rather than
merges when the primary checkout is not in a state where a merge is safe. Every one of those is a
refusal the operator can read, not a silent skip.

**Degradation is honest.** Where the merge cannot happen — no main branch configured, a dirty
checkout, a project that is not a repository — approval still succeeds and coverage reports
`verified, not integrated` or `unknown`, which is exactly what B3 built those states to say. The
failure mode is a true report, never a false one.

## Non-Goals

- **Not GitHub.** PR flows need per-agent credentials the `Agent` model does not have, secret
  storage the Hub does not have, and webhook or polling infrastructure — to close a gap local merging
  closes on its own. GitHub mode is a **later change** and this one leaves the seam for it: evidence
  already records an actor and already has a `review_record` kind, so an observed PR review will
  record through the same path a local acceptance uses. Nothing here may assume an approval arrived
  through an AgentWeave route.
- **Not per-task branches.** It would remove the "merges its ancestors too" property, and it is a
  change to how agents are given workspaces at all — much larger than this, and worth doing only if
  the property turns out to hurt in practice.
- **Not pushing, and not touching any remote.**
- **Not reconsidering the rigor levels.** Whether `contract` earns its place and whether `sketch` is
  a level or just the demotion target is a live question, and a **separate** change. Folding it in
  here would put two arguments in one diff.
- **Not undoing an integration.** A merge that should not have happened is reverted with git, by the
  operator. An automatic un-merge is a bigger and much more dangerous feature.
