---
name: aw-status
description: Show a full AgentWeave collaboration overview — session state, all tasks by status, per-agent inboxes, and watchdog health. Use this to understand what is happening across the entire session.
---

Show the full collaboration status for the AgentWeave session.

**Project:** {project_name}
**Mode:** {mode}
**Principal:** {principal}
**Agents:** {agents_list}

Run the following commands and consolidate the output into a clear summary:

1. `agentweave status` — session state, watchdog health, per-agent task counts
2. `agentweave task list` — all active tasks with status, assignee, and priority
3. `agentweave task list --status under_review` — tasks waiting for review
4. `agentweave inbox` — unread messages for all agents

Present a consolidated summary with:
- **Session health:** watchdog running? transport type?
- **Tasks by status:** how many pending / in_progress / under_review / completed?
- **Who is blocked or waiting?** Any tasks in revision_needed or rejected?
- **Unread messages:** who has messages waiting and from whom?
- **Quality Health** (show only when `quality:` is configured):
  ```
  Quality Health
  ─────────────────────────────────────────
  Settings: review_required=<v> | docs_threshold=<v> | echo_chamber=<v>

  Under review:  N tasks
    - <task-id>: <title> (reviewer: <agent>, waiting: ~<N>min)
  ⚠ Stale (>15min):  <task-id> — ping reviewer or escalate

  revision_needed:  N tasks
    - <task-id>: <title> (assignee: <agent>)

  Missing decision docs:  (check <docs_path>/ for expected docs)
  ```
  If no tasks are under review and no revision needed: "✓ All reviewed tasks clear"
- **Recommended next action:** what should happen next to unblock progress? Factor in stale reviews.
