# InterAgent

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://badge.fury.io/py/interagent-framework.svg)](https://badge.fury.io/py/interagent-framework)

> **A collaboration framework for Claude Code and Kimi Code**

InterAgent lets Claude Code and Kimi Code work together on the same project.
After a one-time setup, you orchestrate everything through **natural language prompts** —
no manual CLI commands required during your session.

---

## How It Works

InterAgent creates a shared `.interagent/` directory that both agents use as a
communication channel. The user acts as the messenger, passing relay prompts between agents.

```
You (setup once)
  └─ interagent init --project "My App" --principal claude

You (natural language)
  └─ "Claude, delegate the auth module to Kimi"

Claude (runs CLI via Bash automatically)
  └─ interagent quick --to kimi "Implement auth module"
  └─ interagent relay --agent kimi
  └─ [shows you the relay prompt to paste into Kimi]

You
  └─ paste relay prompt into Kimi Code

Kimi (reads AGENTS.md + context.md, runs CLI via terminal)
  └─ interagent task update <id> --status in_progress
  └─ [does the work]
  └─ interagent task update <id> --status completed
  └─ interagent msg send --to claude --subject "Done" --message "..."

You
  └─ "Claude, Kimi is done"

Claude (runs CLI via Bash automatically)
  └─ interagent inbox --agent claude
  └─ interagent summary
  └─ [reviews Kimi's work and continues]
```

**The only manual step is pasting the relay prompt into Kimi.** Both agents handle
all CLI commands themselves — you just have a conversation.

---

## Quick Start

### 1. Install

```bash
pip install interagent-framework
```

### 2. Initialize (once per project)

```bash
cd your-project/
interagent init --project "My App" --principal claude
```

This creates:
- `.interagent/AGENTS.md` — full collaboration guide that both agents read on startup
- `.interagent/shared/context.md` — fill this with your project description
- `.interagent/session.json` — session state

### 3. Fill in project context

Edit `.interagent/shared/context.md` and paste in your project description, current state,
and any constraints. Both agents read this at the start of every task.

### 4. Start working — just prompt Claude

From this point, use natural language. Claude handles the CLI:

> "Claude, read `.interagent/AGENTS.md` to understand how we're collaborating,
> then delegate the database schema design to Kimi."

Claude will run `interagent quick` and `interagent relay` via Bash, then show you
a prompt to paste into Kimi Code.

---

## Prompt-First Workflow

### Delegating to Kimi

Just tell Claude what to assign. No CLI needed.

**You → Claude:**
> "Delegate the user authentication module to Kimi. It should include login, logout,
> JWT tokens, and password reset. See PLAN.md for the API design."

**Claude does automatically:**
```bash
interagent quick --to kimi "Implement user authentication: login, logout, JWT tokens, password reset. See PLAN.md §3 for API design."
interagent relay --agent kimi
```

**Claude shows you:**
```
====================================================================
RELAY PROMPT FOR KIMI
====================================================================
Copy and paste this to the agent:

@kimi - You have work in the InterAgent collaboration system.

Your role: delegate
Collaboration guide: read .interagent/AGENTS.md for commands, workflow, and protocol.
Project context: read .interagent/shared/context.md before starting.

[TASK] You have 1 new task(s):
   - Implement user authentication (task-a3f2c1)
...
====================================================================
```

**You:** paste that into Kimi Code.

---

### Kimi Receiving Work

When Kimi receives the relay prompt, it:
1. Reads `.interagent/AGENTS.md` for the full collaboration guide and command reference
2. Reads `.interagent/shared/context.md` for project context
3. Runs `interagent inbox --agent kimi` to see the task
4. Does the work
5. Reports back via `interagent msg send --to claude --subject "Done" --message "..."`

All of this happens automatically — Kimi doesn't need to be told how the system works
because AGENTS.md explains it.

---

### Getting Kimi's Work Back to Claude

When Kimi is done:

**You → Claude:**
> "Kimi is done."

**Claude does automatically:**
```bash
interagent inbox --agent claude
interagent summary
```

Claude reviews Kimi's messages and completed tasks, then continues reviewing or
assigns the next task.

---

### Asking for a Status Check

**You → Claude:**
> "What's the current state of the project?"

**Claude does automatically:**
```bash
interagent status
interagent summary
```

---

### Cross-Agent Sub-Agent Requests

Either agent can ask the other to run one of their specialized sub-agents.

**Example — Claude asking Kimi to do web research:**

Claude writes `.interagent/shared/agent-request-research.md`:
```
Kimi: research latest best practices for JWT refresh token rotation (2026)
Write summary to: .interagent/shared/jwt-research.md
```

Then Claude tells you: *"Tell Kimi to check `.interagent/shared/` for a new request."*

You paste one message into Kimi. Kimi handles it. No further orchestration needed.

---

## Setup for New Projects (Using the Kickoff Template)

If you use the [project kickoff template](https://github.com/gutohuida/InterAgentFramework),
the generated `CLAUDE.md` automatically includes the multi-agent workflow rules:

- Claude checks for `.interagent/session.json` on every session start
- If found, Claude reads `AGENTS.md` and `context.md` automatically
- Claude runs all `interagent` commands via Bash without being asked

This means on any future session, you can start with:
> "Check the InterAgent session and tell me what's pending."

And Claude will handle the rest.

---

## Commands Reference

### Session

```bash
interagent init --project "Name" --principal claude   # Initialize
interagent status                                      # Full status
interagent summary                                     # Quick overview
```

### Delegation

```bash
interagent quick --to kimi "Task description"         # Create + assign task
interagent relay --agent kimi                         # Generate relay prompt
interagent relay --agent claude                       # Generate relay for Claude
```

### Tasks

```bash
interagent task list                                  # List all tasks
interagent task show <task_id>                        # View task details
interagent task update <task_id> --status in_progress
interagent task update <task_id> --status completed
interagent task update <task_id> --status approved
interagent task update <task_id> --status needs_revision --note "Fix X"
```

### Messaging

```bash
interagent inbox --agent claude                       # Check Claude's inbox
interagent inbox --agent kimi                         # Check Kimi's inbox
interagent msg send --to claude --subject "Done" --message "Implemented X"
```

### Template Maintenance

Keep your project kickoff template current with new AI capabilities:

```bash
interagent update-template --agent claude --template-path ~/projects/template.txt
interagent update-template --agent kimi   --template-path ~/projects/template.txt
interagent update-template --agent claude --focus "sub-agents"
```

The generated prompt instructs the agent to search for new best practices,
review the current template, apply improvements, and write a `TEMPLATE_UPDATE.md`.

---

## What Gets Created on Init

```
.interagent/
├── AGENTS.md             # Collaboration guide — both agents read this
├── README.md             # Quick command reference
├── session.json          # Session config (id, mode, principal)
├── shared/
│   └── context.md        # Project state — fill this with your project description
├── tasks/
│   ├── active/           # JSON files for each active task
│   └── completed/        # Archived completed tasks
├── messages/
│   ├── pending/          # Unread messages
│   └── archive/          # Message history
└── agents/               # Agent status files
```

`.interagent/AGENTS.md` is the key file. Both Claude and Kimi read it on every
session start to understand their roles, available commands, and the collaboration protocol.

---

## Safety Features

**File locking** — prevents race conditions when both agents work simultaneously.
Tasks and messages use file-based mutexes with a 5-minute automatic timeout.

**Schema validation** — all JSON state files are validated before saving.
Agent names, task statuses, and required fields are enforced.

**Input sanitization** — string length limits and type coercion before any write.

---

## Watchdog (Optional)

Run in a separate terminal to get notifications when tasks or messages change:

```bash
interagent-watch
```

Useful if you want to know when Kimi has finished without actively checking.

---

## Roles

| Role | Agent | Responsibilities |
|---|---|---|
| Principal | Claude | Architecture, planning, review, final decisions |
| Delegate | Kimi | Implementation, execution, reporting back |

In hierarchical mode (default), Claude assigns work and reviews results.
In peer mode, both agents can assign tasks to each other.

---

## Installation Options

```bash
# From PyPI
pip install interagent-framework

# From source
git clone https://github.com/gutohuida/InterAgentFramework.git
cd InterAgentFramework
pip install -e .
```

---

## FAQ

**Q: Do I need to run CLI commands during my session?**
No. After `interagent init`, just talk to Claude. It runs all `interagent` commands
via Bash automatically. The only manual step is pasting the relay prompt into Kimi.

**Q: How does Kimi know how to use the system?**
`interagent init` writes `.interagent/AGENTS.md` — a complete guide covering commands,
workflow, and protocol. The relay prompt tells Kimi to read it before starting work.

**Q: Should I commit `.interagent/` to Git?**
Partially. The `.gitignore` included with the project excludes runtime state
(tasks, messages, session.json) but keeps AGENTS.md and README.md.
This gives you documentation without committing transient data.

**Q: Can I use this with just Claude (no Kimi)?**
Yes — just skip the relay step. The session, task, and summary commands are
useful even for single-agent projects to track progress.

**Q: What if Kimi doesn't have terminal access?**
The relay prompt includes the task details inline, so Kimi can read and respond
without running any commands. The collaboration is less structured but still works.

---

## Links

- **GitHub:** https://github.com/gutohuida/InterAgentFramework
- **PyPI:** https://pypi.org/project/interagent-framework/
- **Issues:** https://github.com/gutohuida/InterAgentFramework/issues

---

MIT License
