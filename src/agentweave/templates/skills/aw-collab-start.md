---
name: aw-collab-start
description: Orient yourself at the start of an AgentWeave session — read your assigned role from roles.json, check your inbox for unread messages, and list your active tasks. Run this automatically at the beginning of any session in an AgentWeave project.
---

You are working inside an AgentWeave collaboration session. Orient yourself before doing anything else.

**Project:** {project_name}
**Mode:** {mode}
**Principal agent:** {principal}
**All agents:** {agents_list}

Run the following steps in order:

1. Read `.agentweave/roles.json` to find your assigned role in `agent_assignments.<your_name>`, then read the corresponding guide in `.agentweave/roles/<role_key>.md`.
2. Run `agentweave inbox` to see unread messages addressed to you.
3. Run `agentweave task list` to see all active tasks, then filter by your agent name if needed.
4. Read `.agentweave/shared/context.md` for today's focus and any recent decisions.
5. Check `.agentweave/shared/checkpoints/` for any checkpoint file matching your agent name (e.g. `claude-*.md`). If one exists, read the most recent file — your "Next Steps" from the last session is your starting point for this session.

After completing the steps above, briefly report:
- Your assigned role and responsibilities
- Number of unread messages (and from whom)
- Your assigned tasks and their current status
- Any blockers or items needing attention
- Whether you found a prior checkpoint (and if so, what the next step is)

If you are the principal agent ({principal}), also check whether any delegates have completed tasks that need review.
