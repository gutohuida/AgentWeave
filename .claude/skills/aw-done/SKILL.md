---
name: aw-done
description: Mark a task as completed and notify the principal agent. Usage — /aw-done <task-id> ["optional completion note"]
disable-model-invocation: true
---

Mark a task as completed and notify the principal.

**Project:** Agentweave
**Principal to notify:** claude
**Mode:** hierarchical

Parse $ARGUMENTS as: `<task-id> ["optional note"]`

Steps:

1. Run `agentweave task show <task-id>` to display the task details and confirm with the user that this is the correct task.
2. Run `agentweave task update <task-id> --status completed` (include `--note "<note>"` if a note was provided).
3. Run `agentweave msg send --to claude --type message --subject "Completed: <task-title>" --task-id <task-id> --message "Task <task-id> is complete. <note if provided>"`
4. Ask the user: "Does this task need review before it's approved? (yes/no)"
   - If yes: run `agentweave task update <task-id> --status under_review` and update the message subject to "Ready for review: <task-title>"
   - If no: leave status as completed.
5. Check transport: run `agentweave transport status`
   - If transport is **local**: run `agentweave relay --agent claude` and show the relay prompt so the user can hand it off.
   - If transport is **http** or **git**: confirm the notification was delivered automatically.

Report: task ID, final status, whether relay is needed.
