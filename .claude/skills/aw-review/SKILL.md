---
name: aw-review
description: Request a code review from another agent in the AgentWeave session. Usage — /aw-review "<what to review>" ["focus area or specific concern"]
---

Create and delegate a code review task in the AgentWeave session.

**Project:** Agentweave
**Default reviewer:** kimi
**All agents:** claude, kimi, minimax
**Mode:** hierarchical

Parse $ARGUMENTS as: `"<target — file, PR, module, or feature>" ["optional focus or concern"]`

Steps:

1. Confirm the reviewer. Default is **kimi**. If the user specifies a different agent in $ARGUMENTS, use that instead — validate it is in: claude, kimi, minimax
2. Run:
   ```
   agentweave task create --title "Review: <target>" --assignee <reviewer> --priority high --description "Please review <target>. <focus if provided>"
   ```
   Note the task ID from the output.
3. Run:
   ```
   agentweave msg send --to <reviewer> --type review --task-id <task-id> --subject "Review request: <target>" --message "Please review <target>. <focus if provided> Task ID: <task-id>"
   ```
4. Check transport: run `agentweave transport status`
   - If transport is **local**: run `agentweave relay --agent <reviewer>` and show the relay prompt.
   - If transport is **http** or **git**: confirm delivery was automatic.

Report: review task ID, assigned reviewer, next step.
