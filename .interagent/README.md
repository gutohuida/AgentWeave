# InterAgent Session: Test

**ID:** session-3f51ca
**Mode:** hierarchical
**Principal:** claude
**Agents:** claude, kimi, gemini

## Quick Commands

```bash
# Check status
interagent status

# Create task for any agent
interagent task create --title "Task name" --assignee <agent>

# List tasks
interagent task list

# Quick delegation
interagent quick --to <agent> "Implement auth"

# Check inbox
interagent inbox --agent <agent>

# Get relay prompt (for each agent)
# interagent relay --agent claude
# interagent relay --agent kimi
# interagent relay --agent gemini

# Summary
interagent summary
```

## Files

- `session.json` — Session configuration
- `AGENTS.md` — Collaboration guide (read by all agents on session start)
- `ROLES.md` — Agent role assignments (edit freely)
- `agents/` — Agent status
- `tasks/active/` — Active tasks
- `tasks/completed/` — Completed tasks
- `messages/pending/` — Unread messages
- `messages/archive/` — Message history
- `shared/` — Shared context and decisions
