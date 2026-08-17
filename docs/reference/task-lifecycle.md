# Task Status Lifecycle

AgentWeave uses a structured task lifecycle to track work from creation to completion.

## Status Flow

```
pending → assigned → in_progress → completed → under_review → approved
                                             ↘ revision_needed (loops back)
                                             ↘ rejected
```

## Status Definitions

| Status | Meaning |
|--------|---------|
| `pending` | Task created but not yet assigned |
| `assigned` | Assigned to an agent, awaiting start |
| `in_progress` | Agent is actively working on it |
| `completed` | Work finished, awaiting review |
| `under_review` | Being reviewed by assigner or principal |
| `approved` | Review passed, task is done |
| `revision_needed` | Changes required, loops back to `in_progress` |
| `rejected` | Task rejected, will not be completed |

## Transitions

The happy path runs `pending → assigned → in_progress → completed → under_review → approved`, and
`revision_needed` loops back to `in_progress`.

Transitions come from two places, and neither is the CLI:

- **The operator**, on the task board in the app.
- **An agent**, through `update_task(task_id, status)` on the
  [agent tool surface](mcp-tools.md), attributed to the run that called it.

Every transition is recorded with its origin, so a task's history says who moved it and why.

**Approval is gated by evidence.** Approving a task whose requirements are declared by a `gate`-rigor
document integrates nothing until evidence for those requirements has been accepted — the operator is
told there is nothing to merge rather than the task silently completing.

## Task Structure

Tasks include:

- `title` — short summary
- `description` — detailed explanation
- `assignee` — responsible agent
- `assigner` — who created/assigned the task
- `priority` — `low`, `medium`, `high`, or `critical`
- `requirements` — list of requirement strings
- `acceptance_criteria` — list of criteria strings
- `deliverables` — expected outputs
