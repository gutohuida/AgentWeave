<!-- InterAgent AI Context v0.2.0 — run `interagent update-template` to update -->
# AI Workflow Context

> **Purpose:** This file defines the project's DNA — what it is, how it's built, and how to work with it.
>
> **Update frequency:** Monthly, or when the tech stack changes.
>
> **For current work:** See `.interagent/shared/context.md` for today's focus and recent decisions.

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

## Multi-Agent Collaboration

If `.interagent/session.json` exists, you are in multi-agent mode.

**On every session start:**
1. **Read this file** (`AI_CONTEXT.md`) — understand the project
2. **Read `.interagent/AGENTS.md`** — learn the collaboration protocol
3. **Read `.interagent/ROLES.md`** — see who's responsible for what
4. **Read `.interagent/shared/context.md`** — see current focus and recent decisions
5. Run `interagent status` to see pending work

**Rule: run all `interagent` CLI commands via Bash automatically.**
Never ask the user to run CLI commands. They only paste relay prompts.

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

## When Compacting

[Replace with: current phase, modified files, failing tests, active InterAgent task IDs]
