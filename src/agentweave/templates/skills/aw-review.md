---
name: aw-review
description: Request a code review from another agent in the AgentWeave session. Usage — /aw-review "<what to review>" ["focus area or specific concern"]
---

Create and delegate a code review task in the AgentWeave session.

**Project:** {project_name}
**Default reviewer:** {reviewer}
**All agents:** {agents_list}
**Mode:** {mode}

Parse $ARGUMENTS as: `"<target — file, PR, module, or feature>" ["optional focus or concern"]`

Steps:

1. Confirm the reviewer. Default is **{reviewer}**. If the user specifies a different agent in $ARGUMENTS, use that instead — validate it is in: {agents_list}

2. **Echo-chamber guard check** — read `agentweave.yml quality.echo_chamber_guard` (or session data):
   - Determine the implementing agent (task assignee, or the current agent if this is self-review)
   - If `enforce` and reviewer == implementing agent: stop and ask the user to specify a different reviewer
   - If `warn` and reviewer == implementing agent: log — "Warning: reviewer is the same as implementing agent. This reduces review effectiveness."
   - If `off`: skip check

3. Resolve decision doc location: `<docs_path>/<task-id>.md` or `.agentweave/code-docs/<task-id>.md`

4. Create the review task with an enriched description:
   ```
   agentweave task create --title "Review: <target>" --assignee <reviewer> --priority high \
     --description "Review <target>. <focus if provided>

   Review checklist (zero-trust sequence):
   1. Read code first — form independent assessment before reading the decision doc
   2. Dependency check — verify all imports exist on the real package registry
   3. AI security checklist — secrets, overly broad permissions, prompt injection vectors
   4. Test validity — independently derive test coverage, check for echo-chamber
   5. Read decision doc at: <doc-path>
   6. Cross-check code vs. doc claims

   Run /aw-verify <task-id> to execute the structured review."
   ```
   Note the task ID from the output.

5. Run:
   ```
   agentweave msg send --to <reviewer> --type review --task-id <task-id> \
     --subject "Review request: <target>" \
     --message "Please review <target>. Decision doc: <doc-path>. Run /aw-verify <task-id>."
   ```

6. Check transport: run `agentweave transport status`
   - If transport is **local**: run `agentweave relay --agent <reviewer>` and show the relay prompt.
   - If transport is **http** or **git**: confirm delivery was automatic.

Report: review task ID, assigned reviewer, doc path, next step.
