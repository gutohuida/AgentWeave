---
name: aw-collab-start
description: Orient yourself at the start of an AgentWeave session — read your assigned role from roles.json, check your inbox for unread messages, and list your active tasks. Run this automatically at the beginning of any session in an AgentWeave project.
---

You are working inside an AgentWeave collaboration session. Orient yourself before doing anything else.

**Project:** Agentweave
**Mode:** hierarchical
**Principal agent:** claude
**All agents:** claude, kimi, minimax

Run the following steps in order:

1. Read `.agentweave/roles.json` to find your assigned role in `agent_assignments.<your_name>` (or `agent_roles.<your_name>` if present).
2. **Load your role guide.** Try calling the `get_context` MCP tool with your role ID (e.g., `get_context(role="backend_dev")`). If this succeeds, the returned content already includes any project-wide instructions prepended to your role guide — use this as your behavioral context. If `get_context` fails with a transport error (meaning you are on local transport), fall back to reading `.agentweave/project_instructions.md` first (if it exists and is non-empty), then read `.agentweave/roles/<role_key>.md`.
3. Run `agentweave inbox` to see unread messages addressed to you.
4. Run `agentweave task list` to see all active tasks, then filter by your agent name if needed.
5. Read `.agentweave/shared/context.md` for today's focus and any recent decisions.

After completing the steps above, briefly report:
- Your assigned role and responsibilities
- Number of unread messages (and from whom)
- Your assigned tasks and their current status
- Any blockers or items needing attention

If you are the principal agent (claude), also check whether any delegates have completed tasks that need review.
