<!-- InterAgent AI Context v0.1.2 — run `interagent update-template` to update -->
# AI Workflow Context

> This file is deployed by `interagent init` and versioned with the package.
> Run `interagent update-template --agent claude` to generate a prompt that
> keeps this file current with new AI capabilities and best practices.

---

## Project Overview

[Replace with: what this project does, who uses it, key workflows, scale expectations]

## Tech Stack

[Replace with: exact versions, package manager, runtime version]

## Essential Commands

[Replace with: dev, test, build, lint — all copy-pasteable]

## Architecture

[Replace with: key directories and what belongs in each one]

---

## Code Standards

### Quality
- Never skip tests or disable linting to make the build pass
- Write tests alongside implementation, not as an afterthought
- Keep functions under 50 lines — extract helpers when needed
- No `TODO` comments in committed code — implement or open a tracked issue

### Security
- NEVER commit `.env` files, API keys, or credentials
- Validate ALL user input at API/system boundaries — never trust client data
- Use parameterized queries — no string interpolation in SQL
- Sanitize before rendering any user-generated content

### Workflow
- Prefer editing existing files over creating new ones
- Never create new abstractions for single-use operations
- No feature flags, backwards-compat shims, or speculative future-proofing
- Match the style and patterns already established in the codebase

### Token Efficiency
- Use a sub-agent for high-volume operations (test runs, log analysis, doc fetching)
- Summarize command output — do NOT dump raw stdout into context
- When context is near full: `/compact` with current phase, modified files, failing tests
- After 2+ failed correction attempts on the same issue: `/clear` and rewrite the prompt

---

## Sub-Agent Setup

Create these in `.claude/agents/` based on project type. Each agent outputs findings
with severity: CRITICAL / HIGH / MEDIUM / INFO.

### Always Create
- `security-reviewer` — OWASP Top 10, auth flows, secrets exposure, injection risks
- `qa-engineer` — edge case tests, acceptance criteria validation
- `code-reviewer` — maintainability, complexity, naming, style (read-only tools)

### Create If the Project Has a UI
- `ux-reviewer` — WCAG 2.1 AA, UX copy clarity, flow logic

### Create If the Project Has a Database
- `db-specialist` — schema design, indexes, migration safety, query efficiency

### Create If the Project Has a Public API
- `api-designer` — REST/GraphQL conventions, versioning, error responses

### Create If the Project Will Be Deployed
- `devops-reviewer` — CI/CD config, Dockerfile, env var handling, secrets management

---

## Multi-Agent Workflow (InterAgent)

If `.interagent/session.json` exists, you are in multi-agent mode.

**On every session start:**
1. Read `.interagent/AGENTS.md` — collaboration guide and full command reference
2. Read `.interagent/shared/context.md` — current project state and your task
3. Run `interagent status` to see pending work (via Bash — do not ask user to run it)

**Rule: run all `interagent` CLI commands via Bash automatically.**
Never ask the user to run CLI commands. They only paste relay prompts.

### Delegating to Kimi

```bash
interagent quick --to kimi "[task description]"
interagent relay --agent kimi
```

Show the relay prompt output to the user to paste into Kimi Code.

### When User Says "Kimi Is Done"

```bash
interagent inbox --agent claude
interagent summary
```

Review Kimi's work and continue without user input.

### Cross-Agent Sub-Agent Requests

Write `.interagent/shared/agent-request-[topic].md`, then tell user:
"Tell Kimi to check `.interagent/shared/` for a new request from Claude"

---

## When Compacting

[Replace with: current phase, modified files, failing tests, active InterAgent task IDs]
