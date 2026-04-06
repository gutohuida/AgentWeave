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

- `agent_roles` — maps each agent to an array of role keys (e.g., `"claude": ["tech_lead", "backend_dev"]`)
- `agent_assignments` — legacy single-role map (auto-converted to `agent_roles` for backward compatibility)
- `roles` — role definitions with labels and responsibilities

Example:

```json
{
  "version": 2,
  "agent_roles": {
    "claude": ["tech_lead", "backend_dev"],
    "kimi": ["backend_dev"],
    "codex": ["frontend_dev", "ui_designer"]
  },
  "roles": {
    "tech_lead": {
      "label": "Tech Lead",
      "responsibilities_short": "Architecture decisions, code review, integration"
    },
    "backend_dev": {
      "label": "Backend Developer",
      "responsibilities_short": "APIs, database, business logic, server-side"
    },
    "frontend_dev": {
      "label": "Frontend Developer", 
      "responsibilities_short": "UI components, client-side state, styling"
    },
    "ui_designer": {
      "label": "UI Designer",
      "responsibilities_short": "Visual design, component styling, UX polish"
    }
  }
}
```

### Multi-Role Support

Agents can have **multiple roles simultaneously**. This is useful when:

- An agent needs to both architect and implement (e.g., `tech_lead` + `backend_dev`)
- A small team where agents wear multiple hats
- Specialized tasks that cross traditional boundaries

**Managing roles via CLI:**

```bash
# List all agents and their roles
agentweave roles list

# Add a role to an agent
agentweave roles add claude backend_dev

# Remove a role from an agent
agentweave roles remove claude backend_dev

# Set multiple roles (replaces existing)
agentweave roles set claude tech_lead,backend_dev

# List available role types
agentweave roles available
```

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
| `docs_writer.md` | Documentation, guides, READMEs | — |
| `product_manager.md` | Product requirements, prioritization | — |
| `project_manager.md` | Project planning, coordination | — |
| `ui_designer.md` | Visual design, component styling | — |
| `ux_researcher.md` | User research, usability analysis | — |
| `data_engineer.md` | Data pipelines, ETL, warehousing | — |
| `data_scientist.md` | Analytics, ML models, insights | — |
| `mobile_dev.md` | iOS, Android, React Native | — |

Agents read all their assigned role files at session start.

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

### Collaboration Skills

| Skill | Purpose |
|-------|---------|
| `/aw-collab-start` | Orient yourself at session start — check role, inbox, tasks |
| `/aw-delegate` | Delegate a task to another agent |
| `/aw-status` | Show full collaboration overview |
| `/aw-done` | Mark task complete and notify principal |
| `/aw-review` | Request a code review |
| `/aw-relay` | Generate relay prompt for manual handoff |
| `/aw-sync` | Sync context files from `AI_CONTEXT.md` |
| `/aw-revise` | Accept a revision request and move task to in_progress |

### AW-Spec Workflow Skills

| Skill | Purpose |
|-------|---------|
| `/aw-spec-explore` | Explore an idea — think before implementing |
| `/aw-spec-propose` | Create a structured proposal with design and tasks |
| `/aw-spec-apply` | Implement tasks from a proposal |
| `/aw-spec-archive` | Archive a completed change |

### Utility Skills

| Skill | Purpose |
|-------|---------|
| `/aw-checkpoint` | Save context checkpoint before handoffs |
| `/aw-deploy` | Release a new version of AgentWeave |
| `/check-build` | Check GitHub Actions CI build status |

## See Also

- [Session Modes](session-modes.md) — how hierarchical/peer/review modes work
- [Adding New Agents](adding-new-agents.md) — adding support for new agents
