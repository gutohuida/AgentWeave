# Design

## Context

One function composes the sentence — `GateRefusal._merge_detail` (`hub/hub/requirement_gate.py:165-179`)
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

The structured half gains keys and no consumer breaks, and the reason is stronger than round 1 first
wrote it: **nothing reads any key off `unmergeable` at all.** `GateRefusal.unmergeable` is
`List[Dict[str, Any]]`, `to_dict` copies the list wholesale, and `readableApiError`
(`hub/ui/src/api/client.ts:74-108`) returns `detail.message` and nothing else — as does
`mcp_server._readable_detail` on the agent's side. The `paths` and `target_branch` assertions in
`taskIntegration.test.ts` are assertions about the **sentence**, not about the structured half. That
is also why this change is prose-only and still worth the rounds: the sentence is the entire
interface.

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

The wording must also say **which branch** the fresh footprint has to name, because the supersession
that makes the remedy work is per-branch: `integration_targets` keys `newest[target.branch]`, so a
resolution recorded against a *different* branch adds a second target rather than replacing the
stale one, and the refusal survives. This is the sharpest thing round 2 should check at the source.

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

**Pre-authorised default if a round disagrees:** drop D3 and keep D1 and D2, which are the repair
proper. D3 is an addition to a sentence, not a precondition of it.

**Cost if wrong:** a git call per conflicting target on a refusal, and a clause that could mislead if
`is_reachable_from` were unreliable — which is why only `False` speaks and `None` is silent.

### D4 — A missing commit sha degrades to today's sentence, it does not print an empty one

`_check_mergeable` always writes a `commit_sha`, but the refusal body is also constructed by hand in
tests and fixtures — `hub/ui/src/__tests__/taskIntegration.test.ts:49` builds an `unmergeable` entry
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

1. **Does a fresh footprint recorded on the resolved commit reliably carry the same `branch` value as
   the stale one?** `restamp_run_footprints` writes `branch=rev-parse --abbrev-ref HEAD` in the
   agent's checkout (`requirement_evidence.py:908`), and `read_footprint` with an explicit `at`
   writes `_branch_at`, which is `""` when the commit is not exactly one branch's tip
   (`:516-531`). If a resolution can land a footprint with `branch=""` while the stale row names the
   task branch, the per-branch reduction keeps **both** and the remedy fails. Round 2 answers this at
   the source, and if the answer is no, D2's wording has to name what does work instead.
2. **Should the branch-tip sentence also name its commit?** It is true as written and naming the tip
   adds nothing the reader cannot get from `git rev-parse HEAD`. Proposed answer: yes, for symmetry
   and because the reader may not be in that checkout — but it is the one place where the change adds
   words to a sentence that was not broken, and a round may reasonably say no.
3. **Is there any producer of `unmergeable` other than `_check_mergeable`?** Believed not — round 1
   found none — but the change composes prose from keys only that function writes, so the belief
   should be checked rather than carried.
