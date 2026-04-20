---
name: aw-delegate
description: Delegate a task to another agent in the AgentWeave session. Usage — /aw-delegate <agent> "<task description>"
---

Delegate a task to another agent in the AgentWeave collaboration session.

**Project:** {project_name}
**Principal:** {principal}
**Available agents:** {agents_list}

Parse $ARGUMENTS as: `<agent-name> "<task description>"` (agent name first, then the task).

Steps:

1. Validate that the agent name from $ARGUMENTS is one of the available agents: {agents_list}

2. **Echo-chamber pre-check** (if delegating a review task):
   If the task description contains words like "review", "verify", or "check", and `echo_chamber_guard` is set:
   - Read `roles.json` to find who the implementing agent is
   - If `enforce` and <agent> == implementing agent: stop and ask user to specify a different reviewer
   - If `warn` and <agent> == implementing agent: warn but proceed

3. Build the delegation message with quality expectations appended:
   ```
   <original task description>

   Quality requirements (from agentweave.yml):
   - Write tests before implementing (TDD)
   - Decision doc required if non_trivial (docs_path: <path>)
   - Route to reviewer when complete (review_required: <true/false>)
   ```
   Only append this block if `quality:` is configured and non-default settings are active.

4. Run: `agentweave quick --to <agent> "<enriched description>"`
   - This creates a task AND sends a delegation message in one command.
   - Note the task ID printed in the output.

5. Check the transport type by running: `agentweave transport status`
   - If transport is **local** (no Hub or git configured): run `agentweave relay --agent <agent>` and present the relay prompt to the user so they can copy it into the target agent's session.
   - If transport is **http** or **git**: the message was delivered automatically — confirm this to the user and skip the relay step.

6. Report: task ID created, agent assigned, and next action required (relay or automatic delivery).

If $ARGUMENTS is empty or malformed, ask the user: "Which agent should receive the task, and what should they do?"
