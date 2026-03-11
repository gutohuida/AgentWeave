# InterAgent Collaboration Guide

## What This Is

InterAgent is a multi-agent collaboration protocol. Any number of AI agents can work
together on the same project through a shared `.interagent/` directory and optional MCP tools.

**Session mode:** {mode}
**Principal agent:** {principal} — architecture, planning, review, final decisions
**Other agents:** {agents_list} — see `.interagent/ROLES.md` for role assignments

---

## Communication Mode — Check This First

**If you have `send_message` and `get_inbox` as available tools (MCP mode):**
Use them directly. No relay prompts, no manual steps. The watchdog daemon will
automatically notify the other agent's CLI when you send a message.

**If you do NOT have those tools (manual relay mode):**
Use `interagent relay --agent <name>` to generate a relay prompt, then ask the
user to paste it into the target agent's session.

---

## MCP Mode Workflow (zero-relay — preferred)

### Principal ({principal}) sends a task:
```
1. create_task(title, description, assignee="kimi", assigner="{principal}", priority="medium")
2. send_message(from_agent="{principal}", to_agent="kimi",
               subject="New task: <title>", content="<instructions>",
               message_type="delegation", task_id="<id>")
   → watchdog auto-pings kimi's CLI; no user action needed
3. Wait. When kimi replies, get_inbox("{principal}") will return the message.
4. Review → update_task(task_id, status="approved") or status="revision_needed"
```

### Delegate agent reads inbox and works:
```
1. get_inbox("<your-agent-name>")      → returns unread messages
2. mark_read(message_id)               → archive after processing
3. update_task(task_id, status="in_progress")
4. … do the work …
5. update_task(task_id, status="completed")
6. send_message(from_agent="<your-agent>", to_agent="{principal}",
               subject="Done: <title>", content="Summary of what was done",
               message_type="message", task_id="<id>")
   → watchdog auto-pings {principal}'s CLI
```

### Check session state at any time:
```
get_status()        → session info + task counts
list_tasks()        → all active tasks
list_tasks("kimi")  → tasks assigned to kimi
get_task("task-id") → full task details
```

---

## Manual Relay Fallback (when MCP tools are not available)

```bash
# Principal: assign a task and generate the relay prompt
interagent quick --to <agent> "Task description"
interagent relay --agent <agent>      # → copy output, give to user for that agent

# After user says "Agent X is done"
interagent inbox --agent {principal}
interagent summary

# Task management
interagent task show <task_id>
interagent task update <task_id> --status approved
interagent task update <task_id> --status revision_needed --note "Fix X"
interagent task list
```

### Delegate in relay mode:
```bash
interagent inbox --agent <your-agent-name>
interagent task update <task_id> --status in_progress
interagent task update <task_id> --status completed
interagent msg send --to {principal} --subject "Done: <title>" --message "..."
```

---

## On Every Session Start — Read These Files

**1. `AI_CONTEXT.md`** (project root) — versioned best-practices template:
code standards, workflow conventions, sub-agent setup guide.

**2. `.interagent/ROLES.md`** — role assignments (which agent owns which domain).
Check before creating tasks.

**3. `.interagent/shared/context.md`** — current project state:
what the project is, what's been done, constraints, key decisions.

---

## Multi-Person Collaboration (Git Transport with Clusters)

When multiple developers each run their own AI agents on a shared git remote:

```
Alice's workspace: cluster "alice"  →  alice.claude (principal), alice.kimi (backend)
Bob's workspace:   cluster "bob"    →  bob.gemini (frontend),    bob.codex (QA)
```

Setup per developer:
```bash
interagent transport setup --type git --cluster alice
```

Addressing across clusters:
```bash
interagent msg send --to bob.gemini --message "API contract is ready"
interagent msg send --to kimi --message "local-only message"
```

---

## Cross-Agent Sub-Agent Requests

Either agent can ask another to invoke one of their specialized sub-agents:

1. Write `.interagent/shared/agent-request-[topic].md`:
   ```
   {principal}: run security-reviewer on src/auth/login.py
   Focus: SQL injection, session management, credential exposure
   Write findings to: .interagent/shared/security-findings.md
   ```
2. Use `send_message` (MCP) or tell the user (relay) to notify the target agent.

---

## File Reference

```
.interagent/
  session.json          Session config (id, mode, principal, agents)
  AGENTS.md             This file — collaboration guide
  ROLES.md              Agent role assignments (edit freely)
  README.md             Quick command reference
  watchdog.log          Ping activity log (gitignored, machine-local)
  shared/
    context.md          Project state — read this every session
    agent-request-*.md  Cross-agent sub-agent requests
  tasks/
    active/             JSON files for each task
    completed/          Archived completed tasks
  messages/
    pending/            Unread messages
    archive/            Message history
  transport.json        Transport config (machine-local, gitignored)
```
