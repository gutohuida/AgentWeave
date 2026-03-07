# InterAgent Collaboration Guide

## What This Is

InterAgent is a file-based multi-agent collaboration protocol. It lets Claude Code
(principal) and Kimi Code (delegate) work together on the same project through a
shared `.interagent/` directory. The user acts as the messenger between agents —
passing relay prompts from one agent to the other.

**Session mode:** {mode}
**Principal agent:** {principal} — architecture, planning, review, final decisions
**Delegate agent:** {delegate} — implementation, execution, reporting back

---

## How the Workflow Works

```
User: fills .interagent/shared/context.md with project state
Claude: assigns task → generates relay prompt (via Bash)
User: pastes relay prompt into Kimi Code
Kimi: reads task → does work → updates status → sends completion message
User: tells Claude "Kimi is done"
Claude: runs inbox + summary (via Bash) → reviews → approves or reassigns
```

The only manual step is pasting the relay prompt. Both agents run `interagent`
commands via their Bash/terminal tools — never ask the user to run CLI commands.

---

## Claude's Commands (run via Bash automatically)

```bash
# Assign a task to Kimi and generate the relay prompt
interagent quick --to kimi "Task description"
interagent relay --agent kimi      # → copy output, give to user for Kimi

# After user says "Kimi is done"
interagent inbox --agent claude    # see Kimi's messages
interagent summary                 # see what needs review

# Task management
interagent task show <task_id>     # view full task details
interagent task update <task_id> --status approved
interagent task update <task_id> --status needs_revision --note "Fix X"
interagent task list               # list all tasks

# Overall status
interagent status
```

---

## Kimi's Commands (run via terminal tool automatically)

```bash
# On session start — check what's assigned to you
interagent inbox --agent kimi

# When starting a task
interagent task update <task_id> --status in_progress

# When done
interagent task update <task_id> --status completed
interagent msg send --to claude --subject "Done: <task title>" \
    --message "Implemented X. See kimiwork.md for details."

# View task details
interagent task show <task_id>

# If you need clarification before starting
interagent msg send --to claude --subject "Question: <task title>" \
    --message "Need clarification on Y before starting."
```

---

## Project Context — Read These on Every Session Start

**1. `AI_CONTEXT.md`** (project root) — versioned best-practices template:
- Code standards, security rules, workflow conventions
- Sub-agent setup guide
- Full InterAgent workflow reference
- The basis for this project's `CLAUDE.md`
- Keep it current: `interagent update-template --agent claude`

**2. `.interagent/shared/context.md`** — current project state:
- What the project is and what's been done
- Your specific task or focus for this session
- Constraints, key files, and decisions already made

---

## Cross-Agent Sub-Agent Requests

Either agent can ask the other to run one of their specialized sub-agents:

1. Write a request file: `.interagent/shared/agent-request-[topic].md`
   ```
   Claude: run security-reviewer on src/auth/login.py
   Focus: SQL injection, session management, credential exposure
   Write findings to: .interagent/shared/security-findings.md
   ```
2. Tell the user: "Tell [agent] to check `.interagent/shared/` for a new request"

---

## File Reference

```
.interagent/
  session.json          Session config (id, mode, principal)
  AGENTS.md             This file
  README.md             Quick command reference
  shared/
    context.md          Project state — read this every session
    agent-request-*.md  Cross-agent sub-agent requests
    *-findings.md       Agent output files
  tasks/
    active/             JSON files for each task
    completed/          Archived completed tasks
  messages/
    pending/            Unread messages
    archive/            Message history
  agents/               Agent status files
```
