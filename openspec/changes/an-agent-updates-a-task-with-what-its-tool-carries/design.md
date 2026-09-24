# Design — an agent updates a task with what its tool carries

**Built on the recommended answer to D10/F366**: *the agent's HTTP route is not meant to take
`assignee`; equal capability is restored by refusing `assignee`/`priority`/`description` to run
actors and by adding `requirement_ids`/`spec_document` to the tool.* **If the operator answers
otherwise** (agents may set assignees), the repair flips: `assignee` (and whatever else is chosen) is
added to MCP `update_task` instead, and the author/reviewer guards remain the only protection — which
they are today for the review edge, but not for unassigning another agent's `in_progress` work.

## Context — re-verified on HEAD `404c7d5`

- Route: `agent_actions.py:279-292`, body type `TaskUpdate`, actor `run_actor(actor.run_id,
  actor.agent)`.
- Service: `update_task_for_actor` (`tasks.py:1270`). `loop_id` is refused first (`:1286-1295`) with
  the comment *"Checked before any other field is touched, so a refused update leaves the task
  genuinely unchanged"*; the divergence-policy refusal (`:1414-1424`) sits **after** the transition and
  assignee writes, relying on the uncommitted session being discarded.
- MCP: `update_task(task_id, status, notes)` (`mcp_server.py:337-351`); `_operations()` row fields
  `("status", "notes")` (`agents.py:1110-1117`).
- History: the route has taken the operator's `TaskUpdate` since `28dc801` (*capability phase 1*,
  `git log -S "async def update_shared_task"`); the two-field `_operations()` row dates from `979ff8f`
  (`git log -S 'fields=("status", "notes")'`). Nothing between them narrowed either.

## D1 — Options

1. **Refuse at the service for run actors, per field** (recommended). Mirrors the
   `divergence_policy` precedent, so both adapters and any future caller meet the same rule
   (`agent-capability-plane`: a rule that governs one adapter's callers governs the contract's).
   Refusal is a named 403, not a schema 422, so the agent learns what it can do.
2. **A narrower `AgentTaskUpdate` schema on the agent route.** Also equal, but an extra field becomes
   `422 extra_forbidden` with no reason, and the existing named refusals for `divergence_policy`,
   `escalation_agent` and `blocked_reason` (`test_agent_actions_coordination.py:880-1030`) would all
   degrade to that. Rejected.
3. **Widen the tool to everything the route takes.** Gives agents `assignee` — the harm F366 names.

## D2 — The split, field by field

| Field | Agent | Reason |
|---|---|---|
| `status`, `notes` | yes (unchanged) | the tool's purpose |
| `requirement_ids`, `spec_document` (R2: `spec_document` is not written to the task; it only tells `resolve_identifiers` which document to resolve the ids in, `tasks.py:1431-1433`) | **yes — added to the tool** | the service already records the link as the agent's (`SpecActor(kind="agent")`, `tasks.py:1441-1445`); linking work to requirements is agent work in the spec flow |
| `assignee` | no | staffing is the operator's or a flow's; self-assignment to a review is the bypass F366 names |
| `priority`, `description` | no | the operator's words about the task; an agent's account goes in `notes` |
| `divergence_policy`, `escalation_agent`, `blocked_reason`, `loop_id` | no (unchanged) | existing refusals and sentences kept |

The new check sits beside `loop_id`'s, before any write, and names every offending field present in
the body (`model_fields_set`), so a caller sending two learns both at once.

## D2a — What `update_task_for_actor` returns when what it calls raises

Unchanged paths: `apply_transition` refusals become their existing 4xx; `resolve_identifiers` raises
`LinkRefusedError` → 422. The new check raises before anything else, so it cannot leave a half-applied
update. The divergence-policy check's placement is not moved (out of scope). **R2 confirmed the rollback:**
`get_session` (`db/engine.py:166-169`) only yields inside `async with async_session_factory()`, never
commits, and nothing between the assignee write (`tasks.py:1312`) and that 403 (`:1417`) commits —
`apply_transition` only stages (the comment at `tasks.py:~1377` already relies on this). So a refused
update leaves the row unchanged today; the new check, placed before any write, does not depend on it.

## Round log

- R1 (2026-09-24): written. Not yet compared by R2/R3.
- R2 (2026-09-24): route, service and tool re-read; the field table matches `tasks.py:1286-1446` exactly. No existing test or drive script sends `assignee`/`priority`/`description` on the agent plane (grep). D2a's rollback question answered (it rolls back).
