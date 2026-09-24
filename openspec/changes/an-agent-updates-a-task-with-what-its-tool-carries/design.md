# Design — an agent updates a task with what its tool carries

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B3-2026-09-24.md` §7) verdict was
**REVISE**, for two reasons only; **the operator ruled the change fixed and approved** once they are
applied. **Operator decision:** agents may not set the holder (F366 answered as designed). Agents can
still set holder, priority and description when they **create** a task (`POST /agent-actions/tasks`);
that is filed as **F443**, to be decided later, and is out of this change's scope. Fixes, re-verified
on HEAD `a50a49b`:

- **HIGH — a MODIFIED delta was missing.** `task-lifecycle-governance`'s *"A task entering review
  must not still name its author as its holder"* says, at
  `openspec/specs/task-lifecycle-governance/spec.md:358-361`, that *"The agents' HTTP task route
  accepts an assignee today"*, and its scenario *"Naming a reviewer in the same request succeeds"*
  (`:445-448`) is unscoped, so this change would contradict it for an agent. The delta restates the
  requirement whole: that paragraph is rewritten, the scenario is scoped to the operator, and a new
  scenario says an agent's same-request attempt is refused (task 1.2 already tests it).
- **MEDIUM — `status` is required in MCP `update_task`** (`mcp_server.py:337`,
  `status: TaskStatus`), so adding `requirement_ids` would force a status restatement, and restating
  `blocked` is a 403 for an agent (`tasks.py:1319`). `status` becomes optional in the tool and in its
  `_operations()` row (whose text says *"status is required"*, `agents.py:1116`); the tool sends only
  the keys it was given. The route already treats an absent `status` as "no transition"
  (`if body.status is not None`, `tasks.py:1318`). Test 1.5a.
- **LOW — widen the 403 sentence** to name requirement links as agent work too (D2; spec).

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
the body (`model_fields_set`), so a caller sending two learns both at once. Its sentence (widened by
the operator review) names what an agent *can* write: *"An agent moves its task with status and
notes, and links it to the requirements it serves with requirement_ids; who holds a task, its
priority and its description are the operator's."*

**The tool's `status` becomes optional (operator review).** Today `update_task(task_id, status,
notes=None)` requires `status` and always sends `{"status": ..., "notes": ...}`. With
`requirement_ids` added, an agent linking a requirement would have to restate the status — and an
agent whose task is `blocked` cannot restate `blocked` (403, `tasks.py:1319-1340`). So the tool
takes `status: Optional[TaskStatus] = None` and sends only the keys given; the route skips the
transition when `status` is absent (`tasks.py:1318`), and `notes` is already a no-op when absent
(`:1412`).

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
- R3 (2026-09-24): field table re-derived from `update_task_for_actor` (`tasks.py:1270-1450`) and holds. Note for IMPL: the new check reads `model_fields_set`, so an agent's `"priority": null` (a no-op write today, `:1408`) is refused too — intended, the field is not the agent's. `the-operator-can-rename-a-task` adds `title` to `TaskUpdate`, which this route also takes: whichever lands second adds `title` to this list (both changes say so).
- Operator review (2026-09-24): MODIFIED delta for `task-lifecycle-governance` (paragraph `:358-361`, scenario `:445-448` scoped to the operator); MCP `status` optional; 403 sentence names requirement links; F443 (creation-time fields) filed, out of scope. See the section at the top.
