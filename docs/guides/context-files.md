# Context Files

AgentWeave uses a layered context system to give agents the right information at the right time.

## File Hierarchy

```
Project Root/
├── CLAUDE.md / KIMI.md / GEMINI.md / AGENTS.md   # Agent-specific context (auto-read)
├── AI_CONTEXT.md                                 # Your project DNA (you edit this)
└── .agentweave/
    ├── ai_context.md        # Template source (hidden, don't edit directly)
    ├── protocol.md          # Collaboration protocol
    ├── roles.json           # Agent role assignments (auto-generated)
    ├── roles/               # Per-role behavioral guides
    │   ├── tech_lead.md
    │   ├── backend_dev.md
    │   └── ...
    └── shared/
        └── context.md       # Current focus (changes daily)
```

## Agent-Specific Context Files

Each agent reads a specific file at the project root on session start:

| Agent | File | Notes |
|-------|------|-------|
| `claude` | `CLAUDE.md` | Claude Code specific |
| `gemini` | `GEMINI.md` | Gemini CLI specific |
| All others | `AGENTS.md` | Generic context |

These files are **auto-generated** from `AI_CONTEXT.md` via `agentweave sync-context`.

## AI_CONTEXT.md — Project DNA

This is the **source of truth** for your project. Edit this file to define:

- Tech stack and versions
- Architecture overview
- Coding standards
- Testing requirements
- Deployment process

### Template Structure

```markdown
# AI Context — [Project Name]

## Tech Stack

- Language: Python 3.11
- Framework: FastAPI
- Database: PostgreSQL 15
...

## Architecture

[High-level overview with diagrams if helpful]

## Coding Standards

[Style guide, linting rules, etc.]

## Testing

[What to test, how to run tests, coverage requirements]

## Deployment

[How the project is built and deployed]
```

After editing, regenerate agent files:

```bash
agentweave sync-context
```

## .agentweave/protocol.md

Generated on `init`. Describes:

- Your session mode (hierarchical/peer/review)
- Principal and delegate agents
- MCP vs manual relay workflows

## .agentweave/roles.json

Auto-generated role configuration. Contains:

- `agent_assignments` — maps each agent to their role key (e.g., `"claude": "tech_lead"`)
- `roles` — role definitions with labels and responsibilities

Example:

```json
{
  "version": 1,
  "agent_assignments": {
    "claude": "tech_lead",
    "kimi": "backend_dev"
  },
  "roles": {
    "tech_lead": {
      "label": "Tech Lead",
      "responsibilities_short": "Architecture decisions, code review, integration"
    },
    "backend_dev": {
      "label": "Backend Developer",
      "responsibilities_short": "APIs, database, business logic, server-side"
    }
  }
}
```

To change an agent's role, edit the `agent_assignments` section.

## .agentweave/roles/*.md

Per-role behavioral guides. Available roles include:

| Role File | Description | Default For |
|-----------|-------------|-------------|
| `tech_lead.md` | Architecture, code review, integration | claude |
| `backend_dev.md` | APIs, database, business logic | kimi, codex, qwen |
| `frontend_dev.md` | UI components, client-side state | cursor, windsurf |
| `fullstack_dev.md` | Backend and frontend features | gemini, cline |
| `devops_engineer.md` | CI/CD, infrastructure | opendevin |
| `qa_engineer.md` | Tests, quality assurance | — |
| `security_engineer.md` | Security review, auth | — |
| `architect.md` | System design, API contracts | — |

Agents read their assigned role file at session start.

## .agentweave/shared/context.md

**Dynamic file** — update this daily or when state changes:

```markdown
# Current Project State

## Current Sprint
[MVP development / Refactoring / Release prep]

## Active Work
### In Progress
- [Agent] is working on: [description]

### Next Up
- [Task] — assigned to [agent]

## Recent Decisions
1. [Date] [Decision] — [Rationale]

## Blockers
- [Issue needing attention]
```

## What to Commit

**Safe to commit:**
- `AI_CONTEXT.md`
- `CLAUDE.md` / `KIMI.md` / `GEMINI.md` / `AGENTS.md`
- `.agentweave/protocol.md`
- `.agentweave/roles.json`
- `.agentweave/roles/*.md`
- `.agentweave/shared/context.md`

**Never commit:**
- `.agentweave/session.json`
- `.agentweave/transport.json`
- `.agentweave/tasks/*`
- `.agentweave/messages/*`
- `.agentweave/logs/*`

## Claude Code Skills

When you run `agentweave init`, Claude Code skills are auto-generated in `.claude/skills/`:

| Skill | Purpose |
|-------|---------|
| `/aw-delegate` | Delegate a task to another agent |
| `/aw-status` | Show collaboration status |
| `/aw-done` | Mark task complete and notify principal |
| `/aw-review` | Request a code review |
| `/aw-relay` | Generate relay prompt |
| `/aw-sync` | Sync context files |
| `/aw-revise` | Accept and begin a revision |

## See Also

- [Session Modes](session-modes.md) — how hierarchical/peer/review modes work
- [Adding New Agents](adding-new-agents.md) — adding support for new agents
