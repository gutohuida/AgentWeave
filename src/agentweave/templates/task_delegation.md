# Task Delegation Template

**From:** {{ sender }} ({{ sender_role }})  
**To:** {{ recipient }} ({{ recipient_role }})  
**Date:** {{ date }}  
**Task ID:** {{ task_id }}

---

## Task: {{ title }}

### Description
{{ description }}

### Requirements
{% for req in requirements %}
- [ ] {{ req }}
{% endfor %}

### Acceptance Criteria
{% for criteria in acceptance_criteria %}
- [ ] {{ criteria }}
{% endfor %}

### Priority
{{ priority }}

### Phase
<!-- Which phase of work is being requested? Pick one: -->
- [ ] Explore — read and investigate, produce a findings report. Do NOT modify files.
- [ ] Plan — produce an implementation plan. Do NOT write code. Await approval.
- [ ] Implement — execute the plan. Run tests/lint before marking done.
- [ ] Explore + Implement — full end-to-end (use only for small, well-scoped tasks)

### Constraints
<!-- What the agent must NOT do — scope limits, protected files, off-limits approaches -->
- Do not modify: [files/areas that are off-limits]
- Do not: [specific actions to avoid]

### Output Format
<!-- Exactly what artifact should be produced — be specific -->
- [ ] Code changes in: [list affected files]
- [ ] New file at: [path]
- [ ] Report written to: `.agentweave/shared/[filename].md`
- [ ] Status update only (no file changes)

### Verification
<!-- How the agent can self-check before marking complete — include the exact command to run -->
Run: `[test or lint command]`
Expected: [what passing looks like]
If verification fails: [fix and retry, or escalate to {{ sender }}]

### Escalation Path
<!-- What to do if blocked, uncertain, or scope is larger than expected -->
- Blocked by missing info → use `ask_user` MCP tool (Hub) or send message to {{ sender }}
- Scope larger than expected → stop, report findings, await revised task
- Conflict with constraints above → stop and ask, do not proceed unilaterally

### Context
{{ context }}

### Expected Deliverables
{% for deliverable in deliverables %}
- [ ] {{ deliverable }}
{% endfor %}

---

## Expected Response

Please respond with one of:

- ✅ **ACCEPT** - I can complete this task
- ❌ **REJECT** - I cannot complete this task (explain why)
- ❓ **CLARIFY** - I need more information

Once accepted, please provide:
1. Your approach/plan
2. Estimated time to complete
3. Any dependencies or blockers

---

## Communication

Use the following to update status:

```bash
# Start work
agentweave task update {{ task_id }} --status in_progress

# Add note
agentweave task update {{ task_id }} --note "Making progress..."

# Complete
agentweave task update {{ task_id }} --status completed

# Request review
agentweave msg send --to {{ sender }} --subject "Review Request" --message "Task complete!"
```
