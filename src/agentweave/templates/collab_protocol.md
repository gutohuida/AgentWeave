# AgentWeave Collaboration Protocol

> **Purpose:** How to collaborate with other AI agents in this project.
>
> **Update frequency:** Per session, or when collaboration patterns change.

---

## What This Is

AgentWeave is a multi-agent collaboration protocol. Any number of AI agents can work
together on the same project through a shared `.agentweave/` directory and optional MCP tools.

**Session mode:** {mode}
**Principal agent:** {principal} — architecture, planning, review, final decisions
**Other agents:** {agents_list} — see `.agentweave/roles.json` for role assignments

---

## Communication Mode — Check This First

**If you have `send_message` and `get_inbox` as available tools (MCP mode):**
Use them directly. No relay prompts, no manual steps. The watchdog daemon
automatically pings the target agent's CLI the moment `send_message` is called —
for ALL runner types: native (claude, kimi), claude_proxy (minimax, glm), and manual.

> ⚠ **`agentweave relay`, `agentweave quick`, and `agentweave relay --run` are
> FORBIDDEN in MCP mode.** They require manual human action and defeat the
> purpose of Hub automation. If you find yourself reaching for these commands
> while MCP tools are available, stop and use `send_message` instead.

**If you do NOT have those tools (local/git mode only):**
Use `agentweave relay --agent <name>` to generate a relay prompt, then ask the
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
6. send_message(from_agent="<your-agent>", to_agent="<reviewer-or-principal>",
               subject="Done: <title>", content="Summary of what was done",
               message_type="message", task_id="<id>")
   → watchdog auto-pings the recipient's CLI

**You may message any agent directly.** If a task should be reviewed by someone other than the principal, send the completion message to that agent instead.
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
agentweave quick --to <agent> "Task description"
agentweave relay --agent <agent>      # → copy output, give to user for that agent

# After user says "Agent X is done"
agentweave inbox --agent {principal}
agentweave summary

# Task management
agentweave task show <task_id>
agentweave task update <task_id> --status approved
agentweave task update <task_id> --status revision_needed --note "Fix X"
agentweave task list
```

### Delegate in relay mode:
```bash
agentweave inbox --agent <your-agent-name>
agentweave task update <task_id> --status in_progress
agentweave task update <task_id> --status completed
agentweave msg send --to {principal} --subject "Done: <title>" --message "..."
```

---

## Handoff Message Format (MANDATORY for all A2A messages)

> **Rule:** ALL agent-to-agent messages MUST use this format. No prose preamble ("I've finished..."),
> no postamble ("Let me know if you need anything"), no conversation filler. Start with a field.
> Natural language is for humans only — `ask_user()` and `send_message(to="user")` only.

```
COMPLETED:    [specific deliverables — file paths, endpoints, IDs. NOT "did the work"]
CONTEXT:      [decisions made, constraints found — one line per item max]
REMAINING:    [exact next action for recipient — imperative verb, specific scope]
CONSTRAINTS:  [what recipient must NOT do — omit this field entirely if none]
VERIFICATION: [exact runnable command to confirm correctness]
```

**Format rules:**
- Each field: one or two lines maximum
- No markdown headings, bullet lists, or code blocks inside the fields
- Omit any field that has nothing to say — do not write "N/A" or "None"
- `send_message` subject line: max 80 chars, format `[TYPE] verb noun` e.g. `[DONE] Implement JWT auth`

**Non-compliant (FORBIDDEN):**
```
Hi Kimi! I've finished working on the authentication module. It was quite a challenge
but I managed to get everything working. The JWT implementation is complete and I've
written tests for it. You should be able to build the frontend login form now. Let me
know if you have any questions or if anything needs to be clarified!
```

**Compliant:**
```
COMPLETED:    src/auth/ — POST /login, POST /refresh, DELETE /logout
CONTEXT:      HS256, 1h access token, 7d refresh token in Redis key auth:refresh:<user_id>
REMAINING:    Build frontend login form wired to POST /login; expect {token, refresh_token} in response
CONSTRAINTS:  Do not change token schema — backend validation hard-codes current field names
VERIFICATION: pytest tests/test_auth.py  (expect 12 passed)
```

## A2A Message Length Budget

| Message type | Max lines | Format |
|---|---|---|
| Task delegation | 10 | Handoff format only |
| Task completion | 8 | Handoff format only |
| Blocker / question | 5 | 1 line problem + 1 line context + 1 line ask |
| Status update | 3 | One sentence what changed, one sentence why it matters |

If your message exceeds the budget for its type, you are including information the recipient
does not need. Cut it.

---

## Phase-Based Delegation

When delegating, specify which phase you want. This prevents wasted work if scope is misunderstood.

| Phase | Recipient does | Recipient does NOT |
|-------|---------------|--------------------|
| **Explore** | Reads, investigates, writes findings report | Modifies any files |
| **Plan** | Writes implementation plan to `.agentweave/shared/plan-[task-id].md` | Writes code |
| **Implement** | Executes an approved plan, runs tests | Changes scope without asking |
| **Explore + Implement** | Full end-to-end | (use only for small, well-scoped tasks) |

---

## Escalation Path

If blocked or uncertain at any point:

1. Check `.agentweave/shared/context.md` for recent decisions that may unblock you
2. Send a message to the relevant agent (e.g., {principal} or the assigned reviewer) with the specific question — do not silently stall
3. If Hub transport: use `ask_user` MCP tool for questions that require human input
4. **Do NOT silently skip a blocked task** — update its status to `revision_needed` with a note explaining what is needed

---

## Multi-Person Collaboration (Git Transport with Clusters)

When multiple developers each run their own AI agents on a shared git remote:

```
Alice's workspace: cluster "alice"  →  alice.claude (principal), alice.kimi (backend)
Bob's workspace:   cluster "bob"    →  bob.gemini (frontend),    bob.codex (QA)
```

Setup per developer:
```bash
agentweave transport setup --type git --cluster alice
```

Addressing across clusters:
```bash
agentweave msg send --to bob.gemini --message "API contract is ready"
agentweave msg send --to kimi --message "local-only message"
```

---

## Cross-Agent Sub-Agent Requests

Either agent can ask another to invoke one of their specialized sub-agents:

1. Write `.agentweave/shared/agent-request-[topic].md`:
   ```
   {principal}: run security-reviewer on src/auth/login.py
   Focus: SQL injection, session management, credential exposure
   Write findings to: .agentweave/shared/security-findings.md
   ```
2. Use `send_message` (MCP) or tell the user (relay) to notify the target agent.

---

## File Reference

```
.agentweave/
  session.json          Session config (id, mode, principal, agents)
  protocol.md           This file — collaboration protocol
  roles.json            Agent role assignments (edit freely)
  roles/*.md            Per-role behavioral guides
  README.md             Quick command reference
  ai_context.md         Project DNA source — edit this, then run update-template
  watchdog.log          Ping activity log (gitignored, machine-local)
  shared/
    context.md          Current project state — read this every session
    agent-request-*.md  Cross-agent sub-agent requests
  tasks/
    active/             JSON files for each task
    completed/          Archived completed tasks
  messages/
    pending/            Unread messages
    archive/            Message history
  transport.json        Transport config (machine-local, gitignored)
```

---

## Quick Command Reference

```bash
# Status and overview
agentweave status              # Full status with per-agent breakdown
agentweave summary             # Quick summary for relay decisions

# Task management
agentweave task create --title "Task name" --assignee <agent>
agentweave task list           # List all active tasks
agentweave task show <id>      # Show task details
agentweave task update <id> --status in_progress
agentweave task update <id> --status completed

# Delegation
agentweave quick --to <agent> "Task description"
agentweave relay --agent <agent>   # Generate relay prompt

# Messaging
agentweave inbox --agent <agent>
agentweave msg send --to <agent> --message "..."

# Watchdog (auto-ping daemon)
agentweave start               # Start background watchdog
agentweave stop                # Stop watchdog
agentweave log -f              # Watch log in real-time

# Transport (cross-machine sync)
agentweave transport setup --type git
agentweave transport status
agentweave transport pull
```
