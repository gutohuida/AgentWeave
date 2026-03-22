---
name: aw-relay
description: Generate a relay prompt to hand off pending work to another agent manually. Usage — /aw-relay <agent-name>
---

Generate a relay prompt for a target agent so the user can paste it into that agent's session.

**Project:** {project_name}
**Mode:** {mode}
**Available agents:** {agents_list}

Parse $ARGUMENTS as: `<agent-name>`

If no agent name is provided, ask: "Which agent should receive the relay? Available: {agents_list}"

Steps:

1. Run `agentweave inbox --agent <agent>` to preview unread messages waiting for this agent. Show the output so the user knows what context the agent will receive.
2. Run `agentweave task list --assignee <agent>` to preview tasks assigned to this agent.
3. Run `agentweave relay --agent <agent>` to generate the relay prompt.
4. Present the relay prompt clearly, formatted and ready to copy, with a note:
   > Copy the prompt above and paste it at the start of a new session with **<agent>**.

If the agent has no pending messages or tasks, inform the user: "No pending work for <agent> — relay may not be necessary."
