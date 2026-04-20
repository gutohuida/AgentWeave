---
name: aw-done
description: Mark a task as completed and notify the principal agent. Usage — /aw-done <task-id> ["optional completion note"]
disable-model-invocation: true
---

Mark a task as completed and notify the principal.

**Project:** {project_name}
**Principal to notify:** {principal}
**Mode:** {mode}

Parse $ARGUMENTS as: `<task-id> ["optional note"]`

Steps:

1. Run `agentweave task show <task-id>` to display the task details and confirm with the user that this is the correct task.
2. Run `agentweave task update <task-id> --status completed` (include `--note "<note>"` if a note was provided).
3. **Check quality config** — read `agentweave.yml quality:` section (or `session.json` if no yml):
   - If `docs_threshold` is `all` or `non_trivial`: verify the decision doc exists at `<docs_path>/<task-id>.md` (or `.agentweave/code-docs/<task-id>.md`)
     - If missing: warn the user — "Decision doc not found. Produce it first or routing may be blocked by the reviewer."
   - If `review_required: true`:
     - Determine reviewer: find the agent with `code_reviewer` role in `roles.json`
     - Check `echo_chamber_guard`:
       - `enforce`: verify reviewer ≠ implementing agent (task assignee). If same, `ask_user` to name an alternate.
       - `warn`: log a warning if reviewer == implementer, but proceed
       - `off`: skip check
     - Run `agentweave task update <task-id> --status under_review`
     - Run `agentweave msg send --to <reviewer> --type review --subject "Ready for review: <task-title>" --task-id <task-id> --message "Task <task-id> is ready for review. Decision doc: <doc-path>"`
   - If `review_required: false` (or quality not configured): leave status as completed; send completion message to {principal}
4. Check transport: run `agentweave transport status`
   - If transport is **local**: run `agentweave relay --agent <reviewer-or-principal>` and show the relay prompt.
   - If transport is **http** or **git**: confirm the notification was delivered automatically.

Report: task ID, final status, reviewer assigned (if applicable), whether relay is needed.
