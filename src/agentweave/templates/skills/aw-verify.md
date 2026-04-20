---
name: aw-verify
description: Run the structured zero-trust quality review for a completed task. Performs the full AI-aware review sequence — dependency check, security checklist, test validity, decision doc cross-check — then updates task status to approved or revision_needed with itemized notes. Usage — /aw-verify <task-id>
---

Run the structured quality review for a completed task.

**Project:** {project_name}
**Principal:** {principal}
**Mode:** {mode}

Parse $ARGUMENTS as: `<task-id>`

If no task ID is provided, run `agentweave task list --status under_review` and ask which task to review.

---

## Steps

### 1. Load context

Run `agentweave task show <task-id>` to get:
- Task title, description, assignee (the implementing agent)
- Any existing notes or revision history

Read quality settings from `agentweave.yml` (or `.agentweave/session.json` if no yml):
- `docs_path` — where to find the decision doc
- `docs_threshold` — whether a doc is expected
- `dependency_check` — whether package verification is required

### 2. Locate the decision doc

Resolve the doc path:
- If `docs_path` is set: `<docs_path>/<task-id>.md`
- If not set: `.agentweave/code-docs/<task-id>.md`

Note whether the doc exists. **Do not read it yet.**

### 3. Read the code first (zero-trust)

Read the files listed in the task description or find them from the git diff since the task was started.

Form an independent assessment — **before reading the decision doc**:
- What does this code actually do?
- Is the logic correct? Does it handle error cases?
- Does it fit the existing codebase patterns?

Record your independent findings as working notes.

### 4. Dependency check (if `dependency_check: true` or by default for AI-generated tasks)

For every import or new dependency introduced:
- Verify it exists on the real package registry (PyPI for Python, npm for JS/TS, etc.)
- Check: is the publisher credible? When was the package first published?
- Flag any package that cannot be independently verified

If a hallucinated or unverifiable package is found:
→ Stop review, set task to `revision_needed`, notify PM and `ask_user` immediately

### 5. AI security checklist

Scan the changed files for:

**Hardcoded secrets**
- API keys, tokens, passwords, connection strings embedded in source code
- Pattern: `grep -rE "(api_key|password|secret|token)\s*=\s*['\"][^'\"]{8,}" <files>`

**Overly broad permissions**
- IAM wildcards, CORS `Access-Control-Allow-Origin: *`, file permissions 777/666
- Database grants with ALL PRIVILEGES or equivalent

**Prompt injection vectors**
- External input (user input, file content, API responses) passed unsanitized into: shell commands, `eval()`, SQL queries, LLM prompt strings, template engines

Flag any finding with: what it is, where it is (file:line), severity, suggested fix.

### 6. Test validity check (echo-chamber)

Without looking at the existing tests first:
- Independently derive what the tests *should* cover for this feature
- List: happy path, error paths, 2–3 important boundary conditions

Then read the existing tests:
- Do they cover what you derived?
- Spot-check: mentally mutate 2–3 key branches — would a test catch the break?

If tests exist only for the happy path, or would not catch obvious mutations → flag as insufficient.

### 7. Read the decision doc

If the doc exists, read it now:
- `requirement` field: does the code match what was asked for?
- `## What Was Done`: does the code implement what is claimed?
- `## Why This Approach`: is the reasoning sound? Does the code reflect it?
- `## Alternatives Considered`: were meaningful alternatives evaluated?

**Cross-check**: code vs. doc claims. Any discrepancy is a flag.

If the doc is missing and `docs_threshold` applies → add to findings.

### 8. Compile findings and update task

**If all checks pass** (no blockers, doc matches, tests valid, no security issues):

```bash
agentweave task update <task-id> --status approved --note "Review complete. [brief summary of what was verified]"
agentweave msg send --to {principal} --type message --subject "[APPROVED] <task-title>" --task-id <task-id> \
  --message "COMPLETED: task-id approved after zero-trust review. No blockers found."
```

**If any blocking issue found**:

List each issue separately:
```
Issue 1: [what it is]
  Location: [file:line if applicable]
  Why it matters: [impact]
  Suggested fix: [specific action]

Issue 2: ...
```

```bash
agentweave task update <task-id> --status revision_needed --note "<itemized issues>"
agentweave msg send --to <implementing-agent> --type message --subject "[REVISION] <task-title>" \
  --task-id <task-id> --message "COMPLETED: revision_needed
CONTEXT: [number] issues found
REMAINING: fix each issue listed in task notes, then re-submit for review
VERIFICATION: agentweave task show <task-id>"
```

### 9. Check transport and relay if needed

Run `agentweave transport status`:
- If **local**: run `agentweave relay --agent <implementing-agent-or-principal>` and show the relay prompt
- If **http** or **git**: confirm delivery was automatic

---

## Guardrails

- Always read code **before** the decision doc — independent assessment is the point
- Never approve because you don't want to slow the team down
- Never approve code with hardcoded secrets, hallucinated packages, or unverifiable dependencies
- List every blocking issue separately — vague notes ("looks wrong") are not actionable
- If the decision doc is missing on a non-trivial task, that is itself a blocking issue
- Do not fix the implementation yourself — report and let the implementing agent fix it
