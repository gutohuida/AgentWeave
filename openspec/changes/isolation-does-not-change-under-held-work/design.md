# Design — isolation does not change under held work

**Built on the recommended answer to D12's first question** (F242: *may `read_only` flip
mid-task?*): **no — refused while the agent holds work, allowed otherwise.** If the operator answers
otherwise:

- **"Yes, and the flip takes effect at the next task"** — D1 is replaced by a pin: a task records
  its workspace scheme when its checkout is provisioned (`Task.workspace_scheme` already exists for
  the grandfathered case), and `resolve_turn_workspace` honours the pin over a later `read_only`.
  Larger: it changes task 4.7's precedence.
- **"Yes, freely"** — no change; F242 is closed as accepted behaviour and the settings-page comment
  is rewritten to say the API allows it.

## D12, first question — options

| Option | Releases | Breaks or leaves |
|---|---|---|
| **(a) refuse while the agent holds work** (recommended) | the UI comment's promise holds on every door; an operator is told what to finish first; no stored state changes meaning | an operator who wants to flip a busy agent must wait or reassign |
| (b) pin the scheme per task at provisioning | the flip is always accepted | changes `resolve_turn_workspace`'s precedence (task 4.7, "a task checkout it may not write to would be an empty gesture"); a read-only agent would then write in a task checkout — the opposite of what read-only means |
| (c) snapshot every held checkout at the flip, then allow | nothing is stranded at the moment of the flip | the next task-bound turn still writes uncommitted into the operator's checkout (F242 consequences 2 and 3 are untouched) |

**Interaction with D12's other questions.** None of substance. F165's spelling is about how a
footprint names a branch; F242 decides which directory a read-only agent's turn runs in. A
read-only agent's evidence is footprinted at its recorded directory, the project root
(`footprint_root`'s first answer), under either answer here. F141 does not touch agents.

## D1 — the rule

```python
async def _isolation_change_refusal(session, project_id, agent_row, new_config) -> Optional[dict]:
    before = worktrees.is_writing_agent(agent_row.config or {})
    after = worktrees.is_writing_agent(new_config)
    if before == after:
        return None
    live = [run for run in <agent's Run rows whose id is in run_liveness.live_run_ids()>]
    held = [task for task in <Task where project_id, assignee == agent, status not in TERMINAL_STATUSES>]
    if not live and not held:
        return None
    return {"code": "isolation_change_under_held_work", "message": …, "held": {...}}
```

- **Both directions.** Turning isolation **on** mid-task strands the other way: the previous turns'
  uncommitted edits sit in the operator's checkout while the next turn provisions a fresh task
  checkout from the base and does not see them.
- **Assigned, not provisioned.** A pending or assigned task may have no checkout yet, and counting it
  is stricter than necessary. It is also what the operator can see and act on without reading the
  disk, and the remedy is the same. R2 may narrow it to `provisioned` (`_task_checkouts`,
  `api/v1/worktrees.py:233-290`, computes it from pure path functions) if it argues the strictness
  costs something real.
- **The per-agent worktree** needs no separate check. Its uncommitted work exists only during a turn
  — `snapshot_worktree` commits it when each turn ends — so the live-run check covers it.
- **A review is not held work.** A reviewer is not the task's assignee, and its review checkout is
  detached and per-agent; a live review is covered by the live-run check.

Where it runs: `patch_agent`, after the config merge is computed and before it is assigned
(`agents.py:2648-2659`), so `config: null` (which clears `read_only`) is covered; and
`register_agent`'s re-registration branch (`:2300-2308`).

## What the routes return when what they call raises

The helper reads the registry (in-memory) and one `Task` query. A database error propagates as
today's 500 from either route, with nothing assigned — the check runs before the row is mutated.
The refusal is raised before `session.commit()`, so a refused body changes **no** field, not only
`config` — the same "refused whole" rule the route already states for unknown fields
(`agents.py:2548-2553`).

## Cross-bundle

`agents-no-longer-register-themselves` (bundle B3) deletes `POST /agents/register`. If it lands
first, this change's guard on that route and its task 1.4 are dropped; if this lands first, B3
deletes the guard with the route. B3's design already records this (its *Cross-bundle* list). The
`PATCH` door is untouched by B3.

## Open questions

1. **A read-only agent created that way and assigned a writing task** (R1 finding, not F242's
   door). Options: (a) refuse assigning a task to a read-only agent; (b) give a task-bound turn its
   task checkout even for a read-only agent (reverses task 4.7); (c) snapshot the project checkout
   after a read-only agent's task-bound turn — writes a commit onto the operator's branch; (d) file it
   and leave it. R1 recommends (d) now — nothing in the app sets `read_only` — and (a) if the app ever
   offers it.

## Round log

- **R1, 2026-09-24.** Re-verified F242 against `404c7d5`; found the second door (`POST /register`)
  and the flip-independent residual; wrote D1 and the options.
