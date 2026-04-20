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
3. **Determine the agent's role** — read `.agentweave/roles.json` to find `agent_assignments.<agent>`.
4. **Role-aware context additions** (append to relay output after the standard prompt):

   **If the agent's role is `code_reviewer`:**
   - Read `agentweave.yml` (or `session.json`) `quality:` section and note `docs_path` (default `.agentweave/code-docs`).
   - List any tasks in `under_review` status assigned to this agent: `agentweave task list --status under_review --assignee <agent>`
   - Append to relay:
     ```
     Quality context for your review queue:
     - Decision docs are at: <docs_path>/<task-id>.md
     - Use /aw-verify <task-id> for the structured zero-trust review sequence.
     - Read the decision doc AFTER reading the code — never before.
     ```

   **If the agent's role is an implementing role** (`backend_dev`, `frontend_dev`, `fullstack_dev`, or similar):
   - Read `agentweave.yml` (or `session.json`) `quality:` section.
   - Append to relay only if `quality:` is configured with non-default settings:
     ```
     Quality expectations for this session:
     - Write tests before implementation (TDD).
     - Produce a decision doc at <docs_path>/<task-id>.md before marking tasks complete
       (threshold: <docs_threshold>).
     - Route to reviewer when done using /aw-done.
     ```

   **If quality is not configured:** skip role-aware additions entirely.

5. Run `agentweave relay --agent <agent>` to generate the relay prompt.
6. Present the combined relay prompt (standard + role-aware additions) clearly, formatted and ready to copy, with a note:
   > Copy the prompt above and paste it at the start of a new session with **<agent>**.

If the agent has no pending messages or tasks, inform the user: "No pending work for <agent> — relay may not be necessary."
