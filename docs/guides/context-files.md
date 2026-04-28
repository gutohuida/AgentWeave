# Context Files

AgentWeave uses a layered context system to give agents the right information at the right time.

## File Hierarchy

```
Project Root/
├── CLAUDE.md / GEMINI.md / AGENTS.md             # Agent-specific context (auto-read)
└── .agentweave/
    ├── ai_context.md        # Your project DNA source
    ├── context/             # Per-agent context profiles injected by runners
    │   ├── claude.md
    │   └── kimi.md
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
| `claude_proxy` runners | `CLAUDE.md` | Proxy agents run through Claude Code |
| All others | `AGENTS.md` | Generic context |

These files are generated from `.agentweave/ai_context.md` via `agentweave sync-context`. The command also writes `.agentweave/context/<agent>.md`, which combines project instructions, the AgentWeave protocol, team directory, assigned role guides, and project context for runner-level context injection.

## .agentweave/ai_context.md — Project DNA

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

Running `agentweave activate` also regenerates context files as its final step.

## .agentweave/protocol.md

Generated on `init`. Describes:

- Your session mode (hierarchical/peer/review)
- Principal and delegate agents
- MCP vs manual relay workflows

## .agentweave/roles.json

Auto-generated role configuration. Contains:

- `agent_assignments` — maps each agent to a single default role in freshly initialized projects
- `agent_roles` — optional multi-role map used by newer role-management flows
- `roles` — role definitions with labels and responsibilities

Example:

```json
{
  "version": 1,
  "agent_assignments": {
    "claude": "tech_lead",
    "kimi": "backend_dev"
  },
  "agent_roles": {
    "claude": ["tech_lead", "backend_dev"]
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
    "code_reviewer": {
      "label": "Code Reviewer",
      "responsibilities_short": "Pull request reviews, style enforcement"
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
| `technical_writer.md` | Documentation, guides, READMEs | gpt |
| `code_reviewer.md` | Pull request reviews, style enforcement | aider, copilot |
| `project_manager.md` | Project planning, coordination | — |
| `data_engineer.md` | Data pipelines, ETL, warehousing | — |
| `ml_engineer.md` | ML models, training pipelines, inference | — |

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
- `CLAUDE.md` / `GEMINI.md` / `AGENTS.md`
- `.agentweave/ai_context.md`
- `.agentweave/context/*.md`
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
| `/aw-sync` | Sync context files from `.agentweave/ai_context.md` |
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
| `agentweave checkpoint` | Save context checkpoint before handoffs (CLI command) |
| `/aw-deploy` | Release a new version of AgentWeave |
| `/check-build` | Check GitHub Actions CI build status |

## See Also

- [Session Modes](session-modes.md) — how hierarchical/peer/review modes work
- [Adding New Agents](adding-new-agents.md) — adding support for new agents
