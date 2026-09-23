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

## What each route returns when this raises

`ensure_task_worktree` is reached only from `trigger_agent_directly`, through
`resolve_turn_workspace`. A git failure other than a conflict is caught in `_catch_up_prerequisites`,
aborted where a merge is in progress, and raised as `IsolationUnavailableError` with the git output,
so the operator route (`POST /agent/trigger`) answers the refusal it already answers for a
creation-time failure, and a queued delivery is counted as it already is. Nothing new reaches a 500.

## Round log

- **R1, 2026-09-24** (bundle B1): re-verified F158 at `404c7d5`; wrote this change with (B)
  recommended.
