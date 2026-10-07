# Proposal — a task checkout catches up with its approved prerequisites

**Round 1, 2026-09-24** (bundle B1). Finding: **F158 (B)**. Re-verified by reading on HEAD
`404c7d5`. **Nothing here is implemented yet.**

**Why this is its own change, and not part of S1.** ROUNDS.md lists F158 under S1 (*"What counts as
attending a task"*, `:366`), but it shares no function, file or question with the attendance work:
it is about what a task's git checkout contains (`worktrees.py`, `task_workspace.py`). It ships
independently of every other B1 change, in any order.

## Why

`ensure_task_worktree` merges a task's prerequisite commits **only when it creates the branch**
(`hub/hub/worktrees.py:537-625`; docstring `:550-552`; the resume arm at `:606-612` re-attaches the
existing branch and merges nothing, and the early return at `:561-591` hands back an existing
checkout unexamined). `_prerequisite_commits` (`task_workspace.py:177-245`) is computed on every
task-bound turn and ignored whenever the branch exists (its own docstring, `:218-222`).

The branch is cut by a task's **first** task-bound turn, and nothing makes that turn wait for the
dependency gate:
- `agent_trigger` asks no dependency gate at all (`grep -n dependency_gate
  hub/hub/api/v1/agent_trigger.py` finds nothing); the gate fires on `-> in_progress`
  (`task_transition_service.py:648`, `dependency_gate.evaluate`), one edge after the checkout exists;
- a peer message naming the task binds the recipient's turn to it (`messages.py:278`,
  `task_id=msg.task_id`), whatever the task's prerequisites;
- `POST /tasks/{id}/dependencies` adds a prerequisite to a task already worked (`tasks.py:1731`).

In each, the checkout was cut without the prerequisite's work, correctly at that moment (an
unapproved prerequisite contributes nothing, `task-dependencies` *A prerequisite that is not yet
approved contributes nothing*). Once it is approved, no later turn adds it, while every surface
reports the dependency satisfied. `task-dependencies` already requires the opposite: *"A task's
isolated checkout SHALL contain the work of every prerequisite the task was permitted to start
on"* (`spec.md:334`). The flow's own path is protected by `candidate_is_startable`
(`scheduler.py:706`); the other three doors are not.

## What Changes

- **Each task-bound turn tops up an existing checkout** (design D1): the commits of **approved**
  prerequisites that the branch does not already contain are merged in before the turn starts.
- **Never destructively** (design D2): only on a clean checkout; a conflict is aborted
  (`git merge --abort`), leaving the branch and files as they were, and the turn is refused with the
  sentence `_merge_prerequisites` already uses, naming the prerequisite.
- **Only approved prerequisites** (design D3). The creation-time seeding keeps its F159 rule
  (accepted evidence of an unapproved prerequisite seeds a new checkout); the top-up does not chase
  a prerequisite that is still moving.

## Capabilities

### Modified Capabilities

- `task-dependencies` — *A task's checkout carries the work it depends on*: holds for an existing
  checkout, not only a new one; never damages it.

## Impact

- `hub/hub/worktrees.py`: `ensure_task_worktree`'s two existing-branch paths; a non-destructive
  sibling of `_merge_prerequisites`.
- `hub/hub/task_workspace.py`: `TurnWorkspace` carries the approved subset separately.
- No migration, no route shape, no UI.
