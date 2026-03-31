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

Typical happy-path transition:

```bash
agentweave task update <task_id> --status assigned
agentweave task update <task_id> --status in_progress
agentweave task update <task_id> --status completed
agentweave task update <task_id> --status approved
```

Requesting revision:

```bash
agentweave task update <task_id> --status revision_needed --note "Fix error handling in auth.py"
```

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
