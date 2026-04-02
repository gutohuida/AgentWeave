---
name: aw-revise
description: Accept a revision request for a task that came back as revision_needed — acknowledge receipt, move the task back to in_progress, and notify the principal. Usage — /aw-revise <task-id> ["what you plan to do"]
---

Accept a revision request and start working on it.

**Project:** Agentweave
**Principal to notify:** claude
**Mode:** hierarchical

Parse $ARGUMENTS as: `<task-id> ["optional description of revision plan"]`

Steps:

1. Run `agentweave task show <task-id>` to display the task details, including any revision notes left by the reviewer. Show this to the user so the scope of the revision is clear.
2. Run `agentweave task update <task-id> --status in_progress --note "Revision started. <plan if provided>"`
3. Run `agentweave msg send --to claude --type message --subject "Revision started: <task-title>" --task-id <task-id> --message "Starting revision on task <task-id>. <plan if provided>"`
4. Check transport: run `agentweave transport status`
   - If transport is **local**: run `agentweave relay --agent claude` and show the relay prompt.
   - If transport is **http** or **git**: confirm the notification was delivered automatically.

Report: task ID, status now in_progress, what the revision covers.

If $ARGUMENTS is empty, ask: "Which task ID needs revision? Run `agentweave task list` to find tasks with status revision_needed."
