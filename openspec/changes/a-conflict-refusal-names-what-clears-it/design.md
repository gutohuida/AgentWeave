# Design

## Context

One function composes the sentence — `GateRefusal._merge_detail` (`hub/hub/requirement_gate.py:166-179`)
— and one function fills the list it reads — `_check_mergeable` (`:322-350`). Nothing else in the
product produces prose about a merge conflict: `task_integration.integrate`'s failure reasons are
git's own stderr on a path that only runs *after* approval (`task_integration.py:463-536`), and the
UI renders the gate's `message` verbatim through `readableApiError` rather than recomposing it
(`hub/ui/src/__tests__/taskIntegration.test.ts:43-56`). So the whole defect and the whole repair live
in two adjacent functions in one module, and no bundle rebuild is implied.

The fact the sentence has to branch on is already resolved and already carried. `merge_targets`
(`task_integration.py:385-409`) answers one of two ways:

| Route | Target's commit | `Target.evidence_id` | Is "resolve on the branch" true? |
|---|---|---|---|
| evidence governs (`evidence_governs` → `integration_targets`) | newest **accepted** footprint per branch | the evidence row's id | **No.** The probe re-reads the same commit forever. |
| evidence does not govern (documentless loop, no requirement link) | `task_branch_tip` | `None`, by construction | **Yes.** The tip moves when the branch moves. |

`_check_mergeable` iterates those targets and throws the distinction away.

## Goals / Non-Goals

**Goals.** A refused party — agent or operator — can read the refusal and take an action that clears
it. The refusal names the commit it judged rather than only the branch it came from. Where the state
is the one that drove `git reset --hard`, the refusal says what is odd about it.

**Non-Goals.** Changing which approvals are refused. Probing the branch where evidence governs.
Recording or accepting evidence on anybody's behalf. F156's `will_merge` vocabulary. Anything about
what an agent is told before it reaches the gate.

## Decisions

### D1 — The provenance travels on the entry, not on the situation

`_check_mergeable` appends `{"named_by_evidence": bool(target.evidence_id), "evidence_id":
target.evidence_id}` alongside the four keys it already writes, and `_merge_detail` groups the
entries by that flag.

The alternative is a route flag on `_MergeSituation` — it already resolves `will_merge` once and
documents why (`requirement_gate.py:265-291`), and `evidence_governs` is a PK `session.get` answered
from the identity map the second time, so it is nearly free. Rejected on truthfulness rather than
cost: the sentence is a claim about *the commit it is judging*, and `Target.evidence_id` is that
commit's own provenance. A situation-level flag says "this project's approvals are governed by
evidence", which is one inference away from what the sentence asserts, and one inference is what
produced F155.

The structured half gains keys and no consumer breaks. **Round 1's stated reason for that was
overstated and round 2 corrects it.** Round 1 wrote *"nothing reads any key off `unmergeable` at
all"*. On the two planes it checked that is true — `to_dict` copies the list wholesale,
`readableApiError` (`hub/ui/src/api/client.ts:74-108`) returns `detail.message` and nothing else, and
so does `mcp_server._readable_detail` (`:111-131`) on the agent's side. But it did not check the
drive harnesses, and there is a reader there: `scripts/drive/t_row17_integration.py:273-282` reads
`unmergeable[0]["commit_sha"]` and `u["paths"]` off the refusal body and asserts on both.

The conclusion survives — the keys are additive, and a reader of `commit_sha` and `paths` is
unaffected by two more — but the *argument* has to be the true one, because this change is being
made about a sentence that was plausible and wrong. What is actually true: **no product-code
consumer reads a key off `unmergeable`; one drive harness reads two of the four, and both keep
their meaning.**

That harness reads the **sentence** too, and more sharply than the UI does:
`t_row17_integration.py:284-288` asserts the message contains both `"resolve"` and `"approve"`,
lowercased. The evidence-route sentence this change writes may contain neither word in that form,
so it is a consumer that this change breaks and that round 1 did not have — see task 3.6.

**Cost if wrong:** two unused keys on a refusal body.

### D2 — The evidence-route remedy ends in `ACCEPT_OR_GRANT`, reused verbatim

The module already names the two ways out of an acceptance-shaped refusal once, deliberately, and
says why: *"accepting evidence is the operator's unless an agent has been granted it, and no agent is
granted it by default. An agent reading this can take neither remedy itself, and saying so is what
stops it retrying"* (`requirement_gate.py:73-80`). That last clause is precisely F155's failure — an
agent retrying because it was not told the remedy was not its to take. The remedy sentence therefore
composes as: resolve the conflict, record evidence naming the resolved commit, then `ACCEPT_OR_GRANT`.

Restating it in different words in a second place is rejected: two wordings for one rule drift, and
the drift lands in the one place that must not be wrong.

### D2a — What the remedy may say about the branch, re-derived (round 2)

Round 1 wrote that the wording *"must say **which branch** the fresh footprint has to name"*. Round 2
checked the supersession at the source and **that instruction is itself unfollowable** — a second
unfollowable remedy, inside the change about unfollowable remedies. Three facts, each read from the
code rather than inferred:

**1. `branch` is derived, never supplied.** There is no branch parameter anywhere on the recording
path. `record` (`requirement_evidence.py:97-190`) takes `kind`, `actor`, `locator`, `summary`,
`task_id`, `workspace`; the `branch` written to `EvidenceFootprint` comes only from
`_apply_footprint` (`:362-388`), fed by a `Footprint` that `read_footprint` (`:463-499`) or
`restamp_run_footprints` (`:905-914`) computed from the repository. A reader told to "name the
branch" has no field to name it in. **The remedy has to name a state the recorder can put itself in,
not a value it can pass.**

**2. On the agent route the state is automatic, and round 1's feared failure cannot occur.**
`_take_footprint`'s named-commit path is gated on the actor: `named = locator_commit(locator) if
actor.kind == "operator" else None` (`:282`). So an agent never reaches `read_footprint(root,
at=…)`, never reaches `_branch_at`, and its branch is always `rev-parse --abbrev-ref HEAD` in the
worktree it was given — which is checked out on the task branch, the same value the stale row
carries. `restamp_run_footprints` re-points the row at turn end with the same
`abbrev-ref HEAD` (`:908`). Both writes agree, `newest[target.branch]` collapses them, the stale row
is superseded. **Open question 1 is answered *yes* for the agent.**

**3. On the operator route it is not automatic, and that is the route the round-1 wording described
most literally.** An operator whose `locator` is the resolved sha — exactly what *"record evidence
naming the resolved commit"* invites, and exactly what F71 made authoritative — gets
`read_footprint(root, at=resolved)` and therefore `_branch_at`, which returns `""` unless the commit
is the tip of **exactly one** local branch (`:516-531`). The resolved commit stops being a tip as
soon as anything is committed on top of it, which the agent's own turn-end snapshot does. `""` and
`"agentweave/task/…"` are distinct keys in `newest: Dict[Optional[str], Target]`
(`task_integration.py:283-286`), so both targets survive and the refusal stands.

So the remedy's branch clause is rewritten as a condition on the repository and on where the
recording is done from: **the resolved commit must be reachable as the tip of the branch the refusal
names, and the evidence must be recorded from a checkout of that branch** — which is what an agent
following the sentence does by construction, and what an operator naming a commit in the locator
must additionally arrange. The delta states the condition, not the field.

### D3 — The judged commit is checked against the branch the refusal names it on

Where the entry names a branch, ask `requirement_evidence.is_reachable_from(root, commit_sha,
branch)`; where it answers `False`, add a clause saying the commit is no longer on that branch.

This is the state the drive reached at step 6, and the one in which the current sentence is at its
worst: the refusal reports a `source_branch` that has been rewritten out from under the commit, so a
reader comparing the refusal against `git log` finds the two disagree and has no way to tell which is
lying. It is also the strongest available signal that branch surgery is not what the gate is watching
— which is the destructive half of the finding.

Cost is one `git merge-base --is-ancestor` per unmergeable entry, on a path that has already run
`merge-tree --write-tree` and is already returning a refusal. `is_reachable_from` returns `None` for
a branch that does not resolve, which is treated as "say nothing" — consistent with `_MergeSituation`'s
rule that not knowing is never a reason to assert.

**Round 2 weighed it as instructed and keeps it, with one thing round 1 did not say: D3 can only
ever fire on the evidence route.** On the branch-tip route the entry's branch is
`worktrees.task_branch_name(task.id)` and its commit is that branch's tip by construction
(`task_integration.py:405-409`), so the commit is trivially reachable and the clause is always
silent. The cost is therefore not paid on the route where it buys nothing, and the clause is not a
second thing the branch-tip sentence has to be read around. That makes D3 cheaper than round 1
argued and it stays.

**Pre-authorised default if a round disagrees:** drop D3 and keep D1 and D2, which are the repair
proper. D3 is an addition to a sentence, not a precondition of it.

**Cost if wrong:** a git call per conflicting target on a refusal, and a clause that could mislead if
`is_reachable_from` were unreliable — which is why only `False` speaks and `None` is silent.

### D4 — A missing commit sha degrades to today's sentence, it does not print an empty one

`_check_mergeable` always writes a `commit_sha`, but the refusal body is also constructed by hand in
tests and fixtures — `hub/ui/src/__tests__/taskIntegration.test.ts:48` builds an `unmergeable` entry
with only `target_branch` and `paths`. Composition guards each optional piece independently rather
than assuming the producer, for the reason `_merge_detail` was made compositional in the first place
(`requirement_gate.py:129-137`): a special case that silently drops the important half is what the
composition replaced.

### D5 — A mixed list produces both sentences

A single task cannot today have both an evidence-named and a branch-tip target: `merge_targets`
returns one shape or the other. The composition groups anyway and emits a sentence per non-empty
group, because the alternative is a rule that is correct only by an invariant stated in a different
module, and `evidence_governs`' five-answer ladder (`task_integration.py:347-382`) is exactly the kind
of thing that grows a sixth answer.

### D6 — Two more properties of the supersession the wording rests on (round 2)

Both read from `integration_targets` and `_targets` (`task_integration.py:219-287`) rather than
assumed, because D2's sentence is only true if they hold.

**"Newest" means most recently *recorded*, not newest commit.** `_targets` orders by
`EvidenceFootprint.observed_at.asc()` and the reduction keeps the last write per branch.
`observed_at` is `default=_now` at row creation (`db/models.py:2462`) and `_apply_footprint` never
touches it — so a restamp corrects a footprint's commit without moving it in the ordering. Fresh
evidence recorded after the stale row therefore sorts after it whatever commit either names. The
sentence must not say "newer commit"; it is a newer *record*.

**Any accepted evidence on that branch supersedes — not only evidence for the same requirement.**
The reduction keys on `target.branch` alone, over every accepted footprint the task reaches through
`TaskRequirementLink`. So the remedy does not require re-demonstrating the requirement the stale row
demonstrated. The delta deliberately does not promise the narrower thing, because a reader who
believed the requirement had to match would think themselves blocked where they are not.

## Risks / Trade-offs

- **The remedy is two actors long.** Resolve, record, then get it accepted. That is genuinely more
  than "resolve and approve", and it is what the product actually requires; shortening it in prose
  would put us back where we started. The mitigation is that both actions are named, and the one the
  agent cannot take says so.
- **The evidence-route sentence is longer.** The refusal is already the longest prose the gate emits.
  Accepted: the measured cost of the short version is an agent resetting a branch.
- **Round 2 must re-derive the supersession claim.** The whole remedy rests on "the newest accepted
  footprint per branch wins". If that is wrong — if the reduction keys on something else, or the
  restamp interferes — the new sentence is as unfollowable as the old one, in a change whose entire
  subject is unfollowable sentences.

## Open Questions

All three were answered by round 2, at the source. They are kept rather than deleted so a later
reader can see what was asked and what the code said.

1. **Does a fresh footprint recorded on the resolved commit reliably carry the same `branch` value as
   the stale one?** **Answered: yes on the agent route, no on the operator route — and the question
   was the wrong shape.** `_take_footprint` gates the named-commit path on `actor.kind ==
   "operator"` (`requirement_evidence.py:282`), so an agent's footprint is always
   `abbrev-ref HEAD` in its worktree and `_branch_at`'s `""` is unreachable for it; the turn-end
   restamp writes the same thing (`:908`). An operator naming the resolved sha in the locator does
   reach `_branch_at`, which answers `""` the moment that commit is not exactly one branch's tip.
   The wrong shape is that `branch` is not a field anybody supplies, so "say which branch to name"
   is not a followable instruction at all. See D2a; the remedy now states a condition on the
   repository and on where the recording is done from.
2. **Should the branch-tip sentence also name its commit?** **Answered: yes, both routes name the
   commit.** The branch-tip target is `task_branch_tip` read at the moment the gate asked
   (`task_integration.py:405-409`), so the tip is exactly the time-varying thing a reader cannot
   reconstruct afterwards: a reader who has pushed since cannot otherwise tell whether the probe saw
   their push. That is a stronger reason than round 1's symmetry argument, and it removes the
   objection that the change adds words to a sentence that was not broken — naming the commit is
   what makes the sentence checkable on both routes.
3. **Is there any producer of `unmergeable` other than `_check_mergeable`?** **Answered: no.**
   `refusal.unmergeable.append` occurs once in the product, at `requirement_gate.py:342`. The only
   other constructions of the list are test and fixture literals — `taskIntegration.test.ts:48`
   builds one with `target_branch` and `paths` only, which is what D4 exists for.
