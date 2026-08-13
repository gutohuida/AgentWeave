# Design — Approved means it is in the product

The whole change is one sentence of behaviour — *the transition into `approved` merges the work* —
and six decisions about what makes that safe. Every decision below exists because the naive version
of that sentence damages someone's repository.

## D1. What is merged is a commit, not a branch

`worktrees.branch_name(agent)` gives `agentweave/<agent>`: **one branch per agent, not per task.** A
builder that worked six tasks has all six on one branch. Merging the branch when task 01 is approved
would ship tasks 02–06 as well, unapproved and unreviewed.

B3 already recorded what to merge instead. Each accepted piece of evidence carries an
`EvidenceFootprint` with `commit_sha` — the commit the work was demonstrated against. `git merge
<sha>` is legal and brings in exactly that commit and its ancestry.

**Rule:** integrate the newest `commit_sha` among the task's *accepted* evidence footprints, per
distinct branch. Evidence awaiting review names nothing to merge; rejected evidence names nothing to
merge.

**The property this leaves:** merging a commit merges its ancestors, which may include earlier
unapproved work on the same branch. This is not introduced here — the commit graph already declares
those commits to be dependencies, and no merge of a descendant can exclude them. Removing it means
per-task branches, which is a change to how agents get workspaces at all. Named as a non-goal, not
pretended away.

**Rejected: cherry-picking the task's own commits.** It rewrites history into a shape no agent
produced, conflicts constantly against the branch it came from, and would make the merged commit
differ from the commit the evidence was accepted against — quietly invalidating the footprint that
justified the merge.

## D2. The main branch is named, never inferred

`requirement_evidence.MAIN_BRANCH_NAMES = ("main", "master")` is tried in order, and its docstring is
right about why that is safe:

> *"`None` when there is no main branch to compare against — unknown, which is not the same as
> `False`. Reporting 'not integrated' for a project that simply does not use a main branch would be
> an accusation about a choice."*

A wrong *guess* in a read-only report costs an `unknown`. A wrong guess in a merge writes commits
into a branch the operator did not choose. Those are not the same risk, and the same constant cannot
serve both.

- `Project.main_branch`, nullable. **Set, it is the merge target. Unset, nothing merges.**
- The existing name list survives as a *suggestion* at project setup: detect, propose, let the
  operator confirm once.
- Reporting behaviour is **unchanged** when `main_branch` is null, so this change does not move any
  existing project's coverage answers by itself.
- Unset is not an error. Approval succeeds, nothing is merged, and coverage says
  `verified, not integrated` — which is true.

## D3. Mergeability is a precondition, not a discovery

`worktrees._merge_tree_conflicts()` already test-merges two refs with `git merge-tree --write-tree`,
touching neither working tree nor index. It exists; it is not called by anything on this path.

The conflict check belongs **in `requirement_gate.evaluate`**, returned in the same `GateRefusal`
that already carries `blocking` and `diagnostics`. A task whose work cannot land is not approvable,
and the operator should learn that in the same breath as "FR-14 has no evidence" — not after the
transition has been recorded and a merge has failed halfway.

This means `GateRefusal` grows a third list. It does **not** mean a second enforcement point: the
gate is still one function, called from one place inside `apply_transition`, which is the property
B4 §3.1 established and this change must not weaken.

**Consequence to accept:** a conflicting branch blocks approval even at `sketch` rigor. That is
correct and deliberate — it is not a claim about verification, it is a statement that the work
cannot go where approval says it goes. Rigor governs proof; this governs possibility.

## D4. The merge never touches the operator's working state

Merging into `main` requires `main` somewhere. The primary checkout is the obvious place and the
dangerous one.

**Preconditions, each producing a stated refusal rather than a silent skip:**

1. `Project.main_branch` is set.
2. The primary checkout has no uncommitted changes **to tracked files**.
3. The primary checkout is **on** the main branch.

**Precondition 2 counts tracked files only, and that is not a detail.** The Hub writes specification
documents into the project directory, so any project that has ever had a document carries untracked
content essentially permanently. The first implementation counted it, and skipped nearly every
merge — while telling the operator to clear a condition they could only clear by committing files
the Hub itself had put there. Untracked files are also not the hazard: `git merge` refuses only over
one it would overwrite, and that refusal is caught and recorded as a failure rather than corrupting
anything. Modified *tracked* files are the real risk, and they are what is checked.

Fail any one and approval still succeeds, the merge does not happen, and a `task_integrations` row
records `skipped` with which precondition failed. The operator can read why and fix it.

For a local-first single-operator app this is the ordinary state: agents work in their own
worktrees, and the primary checkout sits on main. The restriction costs nothing in the normal case
and refuses clearly in the abnormal one.

**Rejected for v1: merging in a temporary worktree** so the primary checkout is never involved. It
is the better long-term answer — it removes preconditions 2 and 3 — but git refuses to check out a
branch that is already checked out elsewhere, so it needs a detached-HEAD merge and a ref update,
which is a materially more delicate operation to get right than `git merge`. Worth doing once the
simple version has been used.

## D5. Merging does not depend on rigor

Rigor answers *who may get this task to `approved`*. Integration is *what `approved` means*. Two
different questions, and coupling them produces a trap: an operator lowering a gate to get past a
blocked task would also, invisibly, stop their work shipping. Nobody would predict that, and B4's own
premise is that demotion is a legitimate recorded decision — not one with hidden costs.

So: a `sketch` document's task merges on approval exactly like a `gate` document's task. The gate
decides whether you *reach* approved. This decides what happens when you do.

## D6. Failure degrades into a true statement

If the merge fails — a conflict that appeared between the gate check and the transition, a git error,
a precondition that stopped holding — **the transition still succeeds** and the failure is recorded.

The task is `approved` and the work is not on main, which is precisely the state B3 built
`verified, not integrated` to describe. The product's answer is already correct for this case without
any new vocabulary.

Rolling the transition back on a merge failure was rejected: it makes an approval decision hostage to
a git operation, and it would mean a repository problem silently reverses a human judgement that the
work is good. The judgement stands; the shipping is what did not happen, and coverage says so.

## D7. Non-repository projects are unaffected

`EvidenceFootprint.kind` is `"git"` or `"paths"`, and the second is first-class by deliberate B3
decision — *"a git-only first cut would leave every non-repository project permanently
unverifiable."*

A `paths` footprint names no commit. There is nothing to merge, nothing is attempted, no refusal is
raised, and integration stays `unknown` as it already does. This change must not make a
non-repository project less approvable than it is today.

## D8. The seam left for GitHub

Nothing here may assume the approval arrived through an AgentWeave route.

`RequirementEvidence` already records an actor, and `review_record` is already an accepted evidence
kind. A later GitHub mode observes a PR review and records it through **the same acceptance path** a
local review uses — a second *source*, not a second *system*. The one design rule that keeps that
possible: never two independent approvals of the same work. Whichever mode is active, exactly one
decision exists and the other surface reflects it.

The integration record accordingly stores *how* the merge happened (`local`), leaving room for a
second value without a schema change to its meaning.

## D9. What this deliberately does not do

- **Does not push.** No remote is contacted, so no credential exists to leak, no protected branch can
  be violated, and no collaborator's history can be rewritten.
- **Does not un-merge.** Reverting a bad merge is `git revert`, by the operator. An automatic undo
  triggered by a status change is far more dangerous than the merge it undoes.
- **Does not change the transition graph or move the gate.** B4 §3.2's deadlock argument is untouched
  and still correct.
- **Does not revisit rigor levels.** A separate change.
