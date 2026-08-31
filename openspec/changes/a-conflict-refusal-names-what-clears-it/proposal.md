## Why

The product tells a refused party to do something that provably cannot clear the refusal, and on
2026-08-31 an agent did exactly what it said, twice, and then ran `git reset --hard` on the branch
holding the only copy of its work.

`_merge_detail` (`hub/hub/requirement_gate.py:165-179`) composes:

> This task's work does not merge cleanly into master: drive1_024543.py. **Resolve the conflict on
> the branch, then approve** — approving is what merges it.

`_check_mergeable` (`requirement_gate.py:322-350`) never looks at the branch. It iterates
`situation.will_merge` — the list `task_integration.merge_targets` produced — and asks
`would_conflict(root, target.commit_sha, main_branch)`, which is
`git merge-tree --write-tree <main_branch> <that exact commit>` (`task_integration.py:427-449`).
Where evidence governs the merge, those commits come from `integration_targets`, i.e. **the
newest accepted evidence footprint per branch** (`task_integration.py:270-287`). So a resolution made
on the branch produces a *new* commit no evidence names, the gate goes on probing the *old* one, and
the answer cannot change however many times the party retries. There is no operator action in that
sentence either: approving again re-runs the same probe on the same commit.

**Driven, finding F155 (severity A, `scripts/drive/FINDINGS.md:11499`).** `alpha`, re-triggered on
`task-5ae53e9b339c` after a second task had landed on `master` first, called
`update_task(status="approved")`, read the sentence, and:

1. `git merge master --no-commit --no-ff`, resolved the conflict by hand, kept both functions;
2. `git commit` → `17aac8e`, a correct merge;
3. `update_task(status="approved")` → **the identical refusal, byte for byte**;
4. `git log`, `git status`, `git diff`, re-read the file and the spec document — all confirming its
   own work was right;
5. `update_task(status="approved")` → **the identical refusal again**;
6. `git reset --hard 5f07663`, then `git rebase master`, resolving the same conflict a second time.

The turn ended with the task still `under_review`, the accepted evidence still naming `5f07663` — by
then an **orphaned commit, not on the branch at all** — and the refusal still reporting
`"source_branch": "agentweave/task/task-5ae53e9b339c"`, a branch from which that commit had just been
detached. The refusal reaches the agent as bare prose: `mcp_server._readable_detail`
(`hub/hub/mcp_server.py:112-131`) returns `detail["message"]` and nothing else, so the sentence *is*
the agent's whole instruction. It reaches the operator the same way, through
`readableApiError` in the UI.

**What actually clears it is nowhere in the product's words.** Record *fresh evidence naming the
merged commit* and have it accepted: `integration_targets`' per-branch reduction keeps the newest
accepted footprint, so the new row supersedes the stale one and the approval merges at once. Driven
in the same session — `ev-a2a689ef080d` with footprint `db8fc6a`, accepted, approval through,
outcome `merged`. One tool call the refusal never mentions.

**And the sentence is not wrong everywhere — which is why it survived review.** Since
`a-loop-declares-whether-it-needs-evidence`, `merge_targets` has two routes
(`task_integration.py:385-409`): where evidence governs, the target is an accepted evidence commit;
where it does not — a task on a documentless loop with no requirement link — the target is
`task_branch_tip`, the branch's own head. On that second route *"resolve the conflict on the branch,
then approve"* is exactly right and exactly followable, because the tip moves when the branch moves.
One sentence is emitted for both, and it is true of the route the fixtures exercise and false of the
route the flow feature exists for. F155 fires only where a second task has already landed on the main
branch and touched the same paths — which is to say, only in multi-task flows, and never in a
single-task fixture. That is why three rounds of spec review and 3,783 unit tests did not have it.

## What Changes

- **The refusal names the commit it judged.** `unmergeable` already carries `commit_sha` in its
  structured half (`requirement_gate.py:342-349`) and `_merge_detail` drops it from the prose. The
  reader is currently told a *branch* conflicts when what was probed is one commit; naming it is what
  makes the next two changes checkable by the person reading them. The convention already exists —
  `_unaccepted_detail` renders `commit_sha[:12]`.
- **The remedy is chosen by where the commit came from, per target.** For a commit named by accepted
  evidence, the remedy is: resolve, then **record evidence naming the resolved commit** and have it
  accepted — which ends in the same two-way-out clause `ACCEPT_OR_GRANT` already states for the
  `unaccepted` refusal, because acceptance is the operator's and an agent reading it must ask rather
  than take. For a branch-tip commit, today's sentence is kept unchanged, because there it is true.
- **The discriminator is a fact about the target, not about the project.** `Target.evidence_id` is
  populated on the evidence route by `_targets` (`task_integration.py:219-267`) and left `None` on
  the branch-tip route by construction (`merge_targets`, `:405-409`, whose comment says so). The
  entry appended to `unmergeable` carries that provenance so the sentence is composed from what the
  gate actually probed, and a mixed list — impossible today, cheap to be right about — produces both
  sentences rather than one guess.
- **Where the judged commit is no longer on the branch it names, the refusal says so.** This is the
  state step 6 of the drive created and the state in which the old sentence is most actively
  misleading: the refusal reports a `source_branch` that no longer contains the commit. One
  `requirement_evidence.is_reachable_from(root, commit, branch)` call on a path that has already run
  `merge-tree` and is already refusing. See design D3 — this is the piece most directly aimed at the
  destructive half of the finding, and the one round 2 should challenge hardest on cost.
- **No behaviour of the gate changes.** The same approvals are refused for the same reasons on the
  same commits. What changes is what the refused party is told to do about it.

## Non-Goals

Stated explicitly, not by omission:

- **The conflict probe is not moved to the branch.** Probing the branch tip where evidence governs
  would refuse or permit on the strength of a commit no reviewer accepted, which is the defect
  `approval-refuses-unaccepted-evidence` shipped to end. The gate is right about *what* it probes;
  it is wrong about what it says.
- **Nothing is auto-recorded and nothing is auto-accepted.** A resolution becoming evidence on the
  agent's behalf, or evidence accepting itself because the conflict cleared, would both make the
  review that gates the merge decorative. The remedy is named, not taken.
- **`integration_targets`' per-branch reduction is not touched.** It is what makes the stated remedy
  work; superseding the stale row is exactly its behaviour.
- **F156 is not in scope.** `integration-preview` answering `will_merge: true` for a task the gate
  refuses is a separate filed finding (`FINDINGS.md:11567`) about a different surface, and it is
  vocabulary on a route that deliberately runs no probe. Fixing it inside this change would blur what
  this one is answerable for. If the rounds find that this change alters that answer, record it.
- **F154 is not in scope**, and neither is the review briefing's silence about the evidence route.
  What an agent is told *before* it hits the gate is a real gap and a different change.
- **No new surface, no new route, no schema change.** `GateRefusal.unmergeable` is
  `List[Dict[str, Any]]` already and gains keys, not a type.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `task-lifecycle-governance`: the merge refusal acquires requirements on what it must say — the
  commit it judged, and a remedy the refused party can actually take, which differs by where the
  commit came from. The existing requirement *Approval is refused when the work cannot be merged
  cleanly* is modified rather than joined by a second one, because a refusal and the words it carries
  are one behaviour and splitting them across two requirements is how they drift apart.
