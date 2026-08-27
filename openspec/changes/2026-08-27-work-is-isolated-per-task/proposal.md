## Why

`hub/hub/task_integration.py:10` opens its module docstring with a guarantee it does not deliver:

> **Merge a commit, never a branch.** … The accepted evidence already names the commit the work was
> demonstrated at; that is what goes in, and anything committed after it stays out.

The last clause is true and the guarantee is false. `integrate()` runs
`git merge --no-ff <commit_sha>` (`hub/hub/task_integration.py:289-299`), and `merge --no-ff` brings
in **every ancestor of that commit not already in the target**. Naming a commit rather than a branch
narrows the tip and nothing else. Because `worktrees.branch_name` (`hub/hub/worktrees.py:144`) is
`agentweave/<agent>`, one builder's branch carries every task it has ever worked on, plus every
end-of-turn auto-snapshot (`worktrees.snapshot_worktree`, `hub/hub/worktrees.py:448`). The first
approval on any of those tasks ships all of them.

Measured live on 2026-08-26 against the `ledger-stress` drive project: one approval merged 13 files
and 16 commits, one of them another task's test file for a task still sitting `assigned`
(`scripts/drive/FINDINGS.md:2579`, finding F58).

**A green test names this guarantee and cannot catch its violation.**
`hub/tests/test_task_integration.py:296`, `test_later_commits_on_the_branch_are_not_merged`, says in
its docstring "If this test fails, approving one task ships another task's unreviewed work". Its
fixture commits the unwanted work *after* the evidence commit (`:307`, `:311`) and asserts it stays
out. A descendant of the target is excluded by every candidate mechanism — merge, cherry-pick range,
squash, per-task branch alike — so the assertion restates git's ancestry ordering rather than the
guarantee. Thirty-three lines below, `test_rode_along_commits_names_what_actually_landed` (`:329`)
builds the *earlier*-commit case (`:342`) and asserts the earlier commit **still lands**. The suite
holds one test whose docstring says the bug cannot happen and one that pins the bug as expected, and
both pass.

**The fix already in the tree makes the blast radius visible, not smaller.**
`commits_riding_along` (`hub/hub/task_integration.py:189`) records what came along,
`TaskIntegration.rode_along_commits` persists it (migration `0089`), and `TaskIntegrationNote.tsx`
renders it as an amber line. The merge is byte-for-byte what it was.

**The cause is that a branch does not correspond to a task**, so no query over the branch can
recover the task. Two narrower mechanisms were rejected on measurement, not on reasoning
(`testbed/f58demo2`, transcript in `openspec/explorations/2026-08-27-per-task-worktrees.md` §3):
cherry-picking a range still ships the other task's work and, in its tighter form, *also drops* a
commit of the approved task's own work; squashing the evidence commit's diff lands the tip and
silently omits the rest of a multi-commit task. Option (c), per-task worktrees, was chosen by the
operator on 2026-08-26 and is what this change implements.

## What Changes

- **The unit of workspace isolation becomes the task, not the agent.** A writing turn about a task
  runs in a checkout provisioned for that task, on a branch that carries that task's work and
  nothing else. A writing turn about no task keeps the per-agent workspace that exists today. The
  workspace is keyed by what the turn is about.
- **The turn's task is resolved before its workspace is chosen.** `resolve_agent_workspace` is
  called at `hub/hub/api/v1/agent_trigger.py:535`; `resolve_bound_task` does not run until `:558`.
  The read moves above the workspace block. Verified read-only rather than assumed: it performs one
  `select` over `InboundQueueEntry` (`run_task_binding.py:218-223`), one `session.get(Task, …)`
  (`:120`), and one conversation-binding read, and writes nothing.
- **A task workspace is cut from the project's integration base and carries its approved
  prerequisites' work.** Today a dependent task inherits its prerequisite's not-yet-merged work only
  by accident — when the same agent holds both, it is literally the same branch. Under per-task
  isolation that accident is gone, so provisioning merges each direct prerequisite's accepted
  evidence commit that is not already reachable. A merge that conflicts refuses the turn and names
  the prerequisite, rather than starting the agent on a base that silently lacks what it was told to
  build on.
- **Work already under way keeps the workspace it started in.** A task that already carries
  committed work on a per-agent branch stays on that branch for the rest of its life. No history is
  split, rewritten, or guessed at. The set of such tasks is fixed at the moment this ships and only
  shrinks.
- **A task workspace is released when its task reaches a terminal status**, after integration has
  run. The checkout directory goes; the branch never does. This is what bounds the number of live
  checkouts.
- **The two tests above are corrected**, in the direction that makes them able to fail:
  `test_rode_along_commits_names_what_actually_landed`'s assertion is **inverted**, not deleted, and
  `test_later_commits_on_the_branch_are_not_merged` gains the earlier-commit case its docstring
  already describes.
- **Surfaces that assume one workspace per agent are updated**: the turn context sentence
  (`api/v1/agents.py:1160`), the agent workspace panel (`api/v1/worktrees.py`,
  `WorktreesPanel.tsx`), evidence footprint resolution (`requirement_evidence.footprint_root`), the
  checkpoint path resolver (`checkpoints.py:373`), and conflict detection
  (`worktrees.list_agent_branches` / `detect_conflicts`), which would otherwise silently report
  nothing because a task branch fails its agent-name parse.

## Non-Goals

- **Re-opening the choice between per-task branches, cherry-picking and squashing.** Decided by the
  operator 2026-08-26 and re-measured in the exploration; both alternatives are recorded in
  `design.md` with the transcripts that rejected them.
- **Splitting existing per-agent branches into per-task histories.** There is no record of which
  commit belonged to which task — that absence *is* F58 — so any split would be a guess.
- **Changing when integration happens, or making it able to block an approval.**
  `hub/tests/test_task_integration.py:14` states "Nothing here may block an approval" and that
  stands.
- **Pushing anything anywhere.** No remote is contacted by any path this change touches.
- **Changing the dependency gate's met-status or the edge it sits on.** It stays `approved`, on
  `-> in_progress` (`hub/hub/dependency_gate.py:31`, `task_transition_service.py:375-380`).
- **Bounding disk by refusing turns or deleting checkouts the operator did not release.**

## Impact

**Affected specs:** `operator-agent-creation`, `run-task-binding`, `task-dependencies`,
`task-lifecycle-governance`, `agent-context-onboarding`, `agent-configuration`.

The exploration guessed `agent-flows`, `agent-run-sandboxing` and `agent-conversation-workspace`
instead. Checked and corrected here: `agent-run-sandboxing`'s boundary requirements are written
against "the run's workspace" without naming how it is keyed, so they hold unchanged;
`agent-conversation-workspace`'s review-checkout requirements (`:1658`, `:1702`, `:1731`) are about
a detached checkout at an evidence commit, which is unaffected because the branch carrying that
commit is never deleted; `agent-flows` states nothing about workspaces. `operator-agent-creation` is
where the isolation guarantee actually lives (`:63`, "the scheduler provisions **that agent's**
isolated worktree"), and it was not on the exploration's list.

**Affected code:** `hub/hub/worktrees.py` (task workspace paths, branch names, provisioning,
release, listing), `hub/hub/api/v1/agent_trigger.py` (binding resolved before workspace),
`hub/hub/task_transition_service.py` (release on terminal status),
`hub/hub/requirement_evidence.py` (`footprint_root`), `hub/hub/checkpoints.py`,
`hub/hub/repo_hygiene.py` (ignore the new checkout root), `hub/hub/api/v1/worktrees.py`,
`hub/hub/api/v1/agents.py`, `hub/ui/src/components/environment/WorktreesPanel.tsx`, and one
database migration for the column recording which task a run's workspace was for.
