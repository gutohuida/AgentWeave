# Design — a task checkout catches up with its approved prerequisites

**Built on the recommended answer to one open question (Q-F158 below): option (B), top-up.** F158's
own entry says *"the candidate repair is still the open decision"*, and the change it was raised
against left it open (`openspec/changes/archive/*a-loop-declares-whether-it-needs-evidence/design.md`,
*"F158 stands, unfixed and out of scope"*). If the operator chooses (A) or (C), D1–D3 are replaced by
that option's paragraph below, and the delta's three new scenarios are replaced accordingly.

## Q-F158 — which repair

| Option | What it does | What it breaks | What it releases |
|---|---|---|---|
| (A) Refuse early | `trigger_agent_directly` refuses a task-bound work turn whose task's dependency gate refuses, before any checkout is cut | every peer message naming a not-yet-startable task is refused on delivery and counted towards abandonment; *"Gating start does not gate assignment"* is read as gating any turn about the task; shape 2 (a dependency declared later) is not covered at all | shape 1 at its root |
| **(B) Top up** | each task-bound turn merges approved prerequisites' commits the branch lacks, non-destructively | a started dependent whose newly approved prerequisite conflicts with its own work is refused until someone reconciles — the requirement's existing rule for a new checkout, extended | both shapes; the requirement's first sentence becomes true |
| (C) Report | the turn context names prerequisite commits the checkout lacks, with the merge command; the agent merges | nothing is enforced; the agent may not merge; the board still says satisfied | the silence, only |

**Recommended: (B).** It is the only option that makes `task-dependencies:334` true for both shapes,
and its one cost is the rule the requirement already applies to a new checkout.

## D1 — Where the top-up runs

In `ensure_task_worktree` (`worktrees.py:537-622`), on both paths that return an existing branch:
the existing directory (`:561-591`, after its three obstruction checks) and the re-attached branch
(`:606-612`, after `worktree add`). A new function `_catch_up_prerequisites(path, task_id,
approved)` merges each commit in `approved` that is not an ancestor of `HEAD`
(`git merge-base --is-ancestor`), in the order given, with `--no-ff` and the same commit identity
`_merge_prerequisites` uses (`:459-535`).

`approved` is a new, separate tuple on `TurnWorkspace` (`task_workspace.py:41-60`), threaded through
`resolve_turn_workspace` (`worktrees.py:776-820`) beside `prerequisites`. Computed by a sibling of
`_prerequisite_commits` that keeps only prerequisites at `dependency_gate.MET_STATUS`
(`task_workspace.py:238-240` is where the existing filter is applied).

## D2 — Never destructive

- **Nothing to merge → nothing happens.** The common case costs one `merge-base` per approved
  prerequisite commit.
- **Uncommitted changes** (`_has_uncommitted_changes`, used by `snapshot_worktree`, `:862-900`) with
  something to merge → refuse, naming the prerequisite and the checkout, without touching it. Turn-end
  snapshots commit an agent's work (`snapshot_worktree`), so this is an operator's hand edit or a
  crash between turns.
- **Conflict** → `git merge --abort`, then refuse with the existing conflict sentence
  (`_merge_prerequisites`' first failure mode). The branch tip and files are as before.
- **Commit missing from the repository** → refuse with `_merge_prerequisites`' second sentence.

A refusal is `IsolationUnavailableError`, which the trigger already turns into its task-checkout
refusal (not agent-wide, counted: `turn_scheduler.py:506-533`'s comment on the task arm). So the
input waits with the sentence, is retried by the next pass, and is given up on at the limit, exactly
as a creation-time conflict is today.

## D3 — Only approved prerequisites

The creation-time seeding keeps `_prerequisite_commits`' rule, including F159's: an unapproved
prerequisite's **accepted evidence** seeds a new checkout (`task_workspace.py:201-215`). The top-up
takes only prerequisites at `approved`. A prerequisite still being worked keeps producing accepted
evidence, and chasing it into a started dependent on every turn would merge work nobody has approved
into a checkout an agent is writing in — the property F159's paragraph defends for the branch-tip
route. `task-dependencies` *A dependency that regresses after a dependent has started does not halt
it* is untouched: a prerequisite leaving `approved` contributes nothing further and removes nothing.

**The cost R1 did not weigh (R2): a refusal locks out the agent that could resolve it.** At
creation a conflict leaves no checkout and nothing is lost. On an existing branch, D2's refusal
repeats on **every** task-bound turn for that task until someone merges by hand in the checkout —
including the turn of the agent that owns the work and is best placed to resolve it — and each
delivery counts towards abandonment. The alternative for the conflict case only (D2'): abort, start
the turn anyway, and name the missing prerequisite commit and the merge command in the turn context,
so the agent merges it (the next turn's `merge-base` check then finds it present). D2' keeps (B)'s
enforcement for every clean case and uses (C)'s mechanism only where enforcing would strand the
task. It departs from `task-dependencies`' rule that a checkout that cannot carry its prerequisites
is refused, for an existing checkout only. **Recommendation stays D2 (refuse), for one rule across
new and existing checkouts; D2' is put to the operator** as a sub-question of Q-F158 (Open for the
operator in the bundle record).

**One pass, not two (R2).** `_prerequisite_commits` already walks the prerequisites and calls
`task_integration.merge_targets` (which spawns `rev-parse` on the branch-tip route) for each. The
`approved` subset is computed in the same loop and returned beside it, not by a sibling that walks
them again.

## What each route returns when this raises

`ensure_task_worktree` is reached only from `trigger_agent_directly`, through
`resolve_turn_workspace`. A git failure other than a conflict is caught in `_catch_up_prerequisites`,
aborted where a merge is in progress, and raised as `IsolationUnavailableError` with the git output,
so the operator route (`POST /agent/trigger`) answers the refusal it already answers for a
creation-time failure, and a queued delivery is counted as it already is. Nothing new reaches a 500.

## Round log

- **R1, 2026-09-24** (bundle B1): re-verified F158 at `404c7d5`; wrote this change with (B)
  recommended.
- **R2, 2026-09-24** (bundle B1): re-derived against the code. Shape 1 confirmed by reading rather
  than a throwaway test: `takes_own_checkout` refuses only no task, a grandfathered scheme and an id
  that cannot be a ref (`task_workspace.py:58-90`), never by status, and `_prerequisite_commits`'
  own docstring records the branch cut at dispatch before the gate (`:209-216`). Held: both
  existing-branch returns (`worktrees.py:561-591`, `:604-610`); `_merge_prerequisites`' two
  sentences (`:459-535`); a task-checkout `IsolationUnavailableError` becomes a counted,
  non-agent-wide refusal (`agent_trigger.py:1012-1023`). Added: the lockout cost of refusing on an
  existing branch, with D2' as an operator sub-question; the approved subset computed in the same
  pass.
- **R3, 2026-09-24** (bundle B1): re-derived against the code. No correction. Held: `_prerequisite_commits` filters by `approved` only on the branch-tip route and calls `merge_targets` per prerequisite (`task_workspace.py:237-245`), so D3's same-pass subset is a second list in that loop; `merge_targets` returns evidence targets regardless of status where evidence governs (`task_integration.py:400-401`), so an approved prerequisite contributes its commits. D2 vs D2' stays an operator sub-question.
