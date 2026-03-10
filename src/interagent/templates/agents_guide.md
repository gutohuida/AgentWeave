# InterAgent Collaboration Guide

## What This Is

InterAgent is a file-based multi-agent collaboration protocol. Any number of AI agents
can work together on the same project through a shared `.interagent/` directory.
The user acts as the messenger — passing relay prompts from one agent to the others.

**Session mode:** {mode}
**Principal agent:** {principal} — architecture, planning, review, final decisions
**Other agents:** {delegate} (and any others listed in `.interagent/ROLES.md`)

Supported agents include Claude Code, Kimi Code, Gemini CLI, Codex CLI, Aider, Cline,
Cursor Agent, Windsurf, Copilot Agent, OpenHands — any agent that can read files and
run terminal commands can participate.

---

## How the Workflow Works

```
User: fills .interagent/shared/context.md with project state
Principal: assigns tasks → generates relay prompt (via Bash)
User: pastes relay prompt into the target agent
Agent: reads task → does work → updates status → sends completion message
User: tells principal "Agent X is done"
Principal: runs inbox + summary → reviews → approves or reassigns
```

The only manual step is pasting the relay prompt. All agents run `interagent`
commands via their Bash/terminal tools — never ask the user to run CLI commands.

---

## On Every Session Start — Read These Files

**1. `AI_CONTEXT.md`** (project root) — versioned best-practices template:
- Code standards, security rules, workflow conventions
- Sub-agent setup guide
- Full InterAgent workflow reference (this is the basis for `CLAUDE.md`)

**2. `.interagent/ROLES.md`** — role assignments for each agent:
- Which agent owns which domain (backend, frontend, QA, etc.)
- Before creating a task, check which agent should own it
- Edit freely or ask any agent to update it

**3. `.interagent/shared/context.md`** — current project state:
- What the project is and what's been done
- Your specific task or focus for this session
- Constraints, key files, and decisions already made

---

## Principal's Commands (run via Bash automatically)

```bash
# Assign a task to any agent and generate the relay prompt
interagent quick --to <agent> "Task description"
interagent relay --agent <agent>      # → copy output, give to user for that agent

# After user says "Agent X is done"
interagent inbox --agent {principal}  # see messages addressed to you
interagent summary                    # see all agents' task status and messages

# Task management
interagent task show <task_id>        # view full task details
interagent task update <task_id> --status approved
interagent task update <task_id> --status revision_needed --note "Fix X"
interagent task list                  # list all tasks
interagent task list --assignee <agent>  # filter by agent

# Overall status
interagent status
```

---

## Delegate Agent Commands (run via terminal tool automatically)

```bash
# On session start — check what's assigned to you
interagent inbox --agent <your-agent-name>

# When starting a task
interagent task update <task_id> --status in_progress

# When done
interagent task update <task_id> --status completed
interagent msg send --to {principal} --subject "Done: <task title>" \
    --message "Implemented X. See details in <file>."

# View task details
interagent task show <task_id>

# If you need clarification before starting
interagent msg send --to {principal} --subject "Question: <task title>" \
    --message "Need clarification on Y before starting."

# Send a message to any other agent
interagent msg send --to <agent> --message "Review my work in <file>"
```

---

## Multi-Person Collaboration (Git Transport with Clusters)

When multiple developers each run their own AI agents on a shared git remote:

```
Alice's workspace: cluster "alice"
  - alice.claude (principal)
  - alice.kimi   (backend)

Bob's workspace: cluster "bob"
  - bob.gemini   (frontend)
  - bob.codex    (QA)
```

Setup per developer:
```bash
interagent transport setup --type git --cluster alice
```

Addressing messages across clusters:
```bash
# Send to Bob's gemini specifically
interagent msg send --to bob.gemini --message "API contract is ready"

# Plain agent name → only reaches agents in your own cluster
interagent msg send --to kimi --message "local message"
```

Each cluster sees all messages on the branch but only processes those addressed
to `{cluster}.{agent}` or plain `{agent}` (intra-cluster).

---

## Cross-Agent Sub-Agent Requests

Either agent can ask another to run one of their specialized sub-agents:

1. Write a request file: `.interagent/shared/agent-request-[topic].md`
   ```
   {principal}: run security-reviewer on src/auth/login.py
   Focus: SQL injection, session management, credential exposure
   Write findings to: .interagent/shared/security-findings.md
   ```
2. Tell the user: "Tell [agent] to check `.interagent/shared/` for a new request"

---

## File Reference

```
.interagent/
  session.json          Session config (id, mode, principal, agents)
  AGENTS.md             This file — collaboration guide
  ROLES.md              Agent role assignments (edit freely)
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
  transport.json        Transport config (machine-local, gitignored)
```
