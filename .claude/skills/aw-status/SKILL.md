---
name: aw-status
description: Show a full AgentWeave collaboration overview — session state, all tasks by status, per-agent inboxes, and watchdog health. Use this to understand what is happening across the entire session.
---

Show the full collaboration status for the AgentWeave session.

**Project:** Agentweave
**Mode:** hierarchical
**Principal:** claude
**Agents:** claude, kimi, minimax

Run the following commands and consolidate the output into a clear summary:

1. `agentweave status` — session state, watchdog health, per-agent task counts
2. `agentweave task list` — all active tasks with status, assignee, and priority
3. `agentweave inbox` — unread messages for all agents

Present a consolidated summary with:
- **Session health:** watchdog running? transport type?
- **Tasks by status:** how many pending / in_progress / under_review / completed?
- **Who is blocked or waiting?** Any tasks in revision_needed or rejected?
- **Unread messages:** who has messages waiting and from whom?
- **Recommended next action:** what should happen next to unblock progress?
