## Why

A reviewer agent cannot see the work it is reviewing. Measured live on 2026-08-23, driving the
product end to end against a real project (`scripts/drive/FINDINGS.md`, F10).

`builder` finished two requirements in its isolated worktree and messaged `critic` to review them.
`critic` tried to read builder's worktree and the workspace boundary refused it:

```
event permission_denied  run-2a499a0a
  {"tool_name": "Bash", "reason": "'/builder' is outside your workspace"}
```

The reviewer did not fabricate a verdict. It reported its own blindness and asked the author to
describe the author's own work:

> "I can't access your branch (agentweave/builder) from my isolated worktree to verify FR-2 and
> FR-3. The evidence points to commit cad5d74… but I need to see the actual code changes. Can you
> either: 1. Confirm the fixes are complete… 2. Or open a note describing exactly what changed…"

That is the one arrangement code review exists to prevent.

**The gap is circular, not incidental.** Isolation is per agent and enforced by `AW_WORKSPACE_DIR`.
Work becomes visible to others only by being integrated into main, and integration happens only on
approval — which is what the review is meant to decide.

**This blocks work already in flight.** `loop-becomes-a-flow` makes `completed` claimable by an
agent that did not complete it, resolves a reviewer, and fires it — sixty tasks of designed work
whose entire point is that a different agent reviews. Nothing in that change addresses whether the
fired reviewer can read the code (grep for worktree, isolation or visibility across it returns
nothing). Without this change, that one ships a reviewer that cannot review.

**Read isolation was never designed; it is a side effect.** Per-agent worktrees exist for three
reasons — parallel writes without conflict, blast radius, and attribution. None of them requires
read isolation. It falls out of a directory-containment check that catches reads and writes alike.
So this change corrects an overreach rather than weakening a guarantee.

## What Changes

**A review turn gets its own checkout of exactly the code under review.**

- A reviewing agent's workspace for that turn is a **git worktree detached at the commit the
  evidence names**, at a Hub-owned deterministic path, keyed by the reviewing agent.
- The reviewer gets full read, grep and **test execution** against that tree. It cannot damage the
  author's worktree, because it is not in it.
- **Detached, with no branch.** A branch invites a commit; detached makes the read-only intent
  legible to git itself (`HEAD detached at <sha>`), so the environment states the reviewer's role
  rather than depending on the prompt to.
- **Exactly one workspace per review turn.** The reviewer's own working worktree is not part of a
  review turn at all, so there is no second directory to confuse it with — the wrong place is
  outside the boundary, which is what enforces it.
- Shared dependencies are symlinked into the review checkout the same way they are for a working
  one, or the reviewer cannot run the suite — which is the whole point.

**Which commit:** the one named by the most recent evidence for the task under review. Where
earlier evidence names a different commit, the reviewer is told so rather than silently handed the
newest.

**`Task.reviewer` stops being decorative.** The field is accepted by the payload today, stored, and
read by nothing; its own description promises resolution "when the task is claimed for review".
`loop-becomes-a-flow` resolves it. This change is what makes the agent it resolves to able to do
the job.

## Impact

- Affected specs: `agent-conversation-workspace` (a review turn's workspace),
  `task-lifecycle-governance` (what a reviewer is given)
- Affected code: `hub/hub/worktrees.py`, `hub/hub/api/v1/agent_trigger.py`,
  `hub/hub/requirement_evidence.py` (reading a footprint's commit)
- **Unblocks:** `loop-becomes-a-flow`
- Not in scope: who may approve (posture), per-task review policy, and auto-dispatch — the first two
  are a later change, the third belongs to `loop-becomes-a-flow`

## Rejected alternatives

**A read-only diff tool** (`read_evidence_diff(evidence_id)` returning the diff of the cited
commit). Smallest possible change, and the footprint data to serve it already exists. Rejected
because a diff cannot answer the questions review turns on — *what else calls this, does it break
the other caller, is there a test that should have caught it* — and because it structurally cannot
**run the tests**. This product's thesis is evidence: an agent records "5 passed" and cites a
commit. A reviewer that cannot execute is reviewing a claim, which is a second opinion on a
paragraph rather than a review.

**Read access to the author's worktree.** Rejected: a live worktree has an index and a HEAD, so
`git checkout`, a stray redirect, or a test that writes a fixture all mutate the author's working
state. "Read-only" is not enforceable through a shell.

**A shared staging branch that everyone can read.** Not bad practice in general — it is how CI
works — but it carries a specific multi-agent hazard: if two authors' unreviewed work lands on one
staging branch, a reviewer runs tests against a tree containing changes by someone other than the
author under review, and a failure is attributed to the wrong agent. The product has no machinery
to disentangle that. The safe version of the idea is an ephemeral per-review branch, which is this
change plus a merge.

**Integrate to main on `completed`, review after, revert on rejection.** Rejected: it inverts the
product's central safety property, that nothing lands in main before it is reviewed.
