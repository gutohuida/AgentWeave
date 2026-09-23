# Proposal — isolation does not change under held work

**Round 1, 2026-09-24** (bundle B5, decision D12's first question). Finding: **F242 (B)**.
Re-verified on HEAD `404c7d5`: still open. Nothing here is implemented.

## Why

Whether an agent works in its own checkout is `config.read_only`
(`worktrees.is_writing_agent`, `hub/hub/worktrees.py:226-230`). The app deliberately offers no
control for it, and says why in writing (`hub/ui/src/components/agents/AgentSettingsPage.tsx:290-294`):
*"flipping an agent with uncommitted work in its worktree to the shared checkout would strand that
work somewhere the agent no longer looks. That belongs in its own change, with a decision about what
happens to the existing worktree."*

The API does not keep that promise. Two routes change an existing agent's config with no check:

- `PATCH /agents/{name}` merges `config` as an RFC 7396 patch (`hub/hub/api/v1/agents.py:2648-2659`).
- `POST /agents/register` on an existing name merges `config` too (`agents.py:2300-2308`).

F242 drove the first, with an agent holding a provisioned task checkout:

1. The agent's workspace view drops the checkout (`get_agent_workspace` returns early for a
   non-isolated agent), though the directory is still on disk.
2. The next task-bound turn runs in the **operator's checkout**: `resolve_turn_workspace`
   (`worktrees.py:776-826`) gives `read_only` precedence over the task binding by design (task 4.7).
3. Nothing commits it. The turn's edits are an uncommitted modification in the operator's working
   tree; the task branch never moves.

## What Changes

- **A change to isolation is refused while the agent holds work** (design D1). Both routes refuse,
  with `409 {"code": "isolation_change_under_held_work", "message": …, "held": [...]}`, a body that
  would change `is_writing_agent(config)` while the agent:
  - has a turn this Hub is executing (`run_liveness.live_run_ids()` ∩ the agent's runs), or
  - is the assignee of a task not in `approved`/`rejected` (the statuses at which a task checkout is
    released, `task_transition_service.TERMINAL_STATUSES`, `:736`).
  The message names each run and task and says what clears it: let the turn end; finish, reassign or
  reject the task.
- A body that sets `read_only` to the value it already has, or changes other config keys, is
  unaffected.
- The app keeps no control (the comment's promise stands). The comment gains the rule it asked for.

## Out of scope — found in R1, not carried

**A read-only agent bound to a writing task writes into the operator's checkout, flip or no flip.**
Consequences 2 and 3 of F242 do not need the flip: an agent **created** with `read_only: true` and
assigned a task gets the same turn workspace (`resolve_turn_workspace`'s precedence) and, with no
worktree, no snapshot. This change closes the mid-task door only. Recorded as design Open Question 1
for the operator to file or decide.

## Impact

- `hub/hub/api/v1/agents.py` (`patch_agent`, `register_agent`, one shared helper)
- `hub/ui/src/components/agents/AgentSettingsPage.tsx` (comment only; no bundle change needed — R2
  confirms comments do not alter the build)
- `openspec/specs/workspace-isolation` (one ADDED requirement)
