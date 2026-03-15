<!-- AgentWeave AI Context v0.3.0 — run `agentweave update-template` to update -->
# AI Workflow Context

> **Purpose:** This file defines the project's DNA — what it is, how it's built, and how to work with it.
>
> **Update frequency:** Monthly, or when the tech stack changes.
>
> **For current work:** See `.agentweave/shared/context.md` for today's focus and recent decisions.

---

## Session Start Checklist (REQUIRED)

**Before doing ANY work, complete these steps in order:**

1. **Read `.agentweave/ROLES.md`** — find your assigned role. This is your ONLY responsibility this session.
2. **Read `.agentweave/AGENTS.md`** — learn the collaboration protocol and who the other agents are.
3. **Read `.agentweave/shared/context.md`** — see current focus and recent decisions.
4. **Read this file** (`AI_CONTEXT.md`) — understand the project stack and standards.
5. **Check for AgentWeave MCP tools** — look for `send_message`, `get_inbox`, `update_task`, `ask_user` in your available tools.
   - If MCP tools are available → use them exclusively for all coordination.
   - If no MCP tools → use `agentweave relay` / `agentweave inbox` CLI commands.
6. **Run `agentweave status`** — see all pending tasks before starting any work.

**Do NOT skip this checklist.** An agent that begins work without reading ROLES.md has no valid role and must stop and complete the checklist.

---

## Role Adherence Rules

**Your role is defined in `.agentweave/ROLES.md`. It is your ONLY responsibility this session.**

### MUST
- Identify your assigned role before taking any action.
- Accept only tasks that fall within your assigned role.
- Report task status through AgentWeave (MCP tools or CLI) — not directly to the user.
- Update task status at every transition (`in_progress` when starting, `completed` when done).
- Ask the principal agent for clarification when task scope is unclear.

### MUST NOT
- Start or claim work outside your assigned role.
- Begin any task before completing the Session Start Checklist above.
- Create tasks outside of AgentWeave's task system.
- Report completion directly to the human when another agent is the intended recipient.
- Skip `update_task` status transitions — every status change must be recorded.

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

---

## Multi-Agent Workflow

**Always check for AgentWeave MCP tools at session start** (`send_message`, `get_inbox`, `update_task`, `ask_user`). Then:

### If MCP tools are available (Hub mode)
- Use `send_message` to route work to other agents — never use CLI relay commands.
- Use `get_inbox` to read incoming tasks and messages.
- Use `update_task` for every status transition.
- Use `ask_user` when a decision requires human input — do not interrupt with direct chat.
- NEVER report task status directly to the user when another agent should receive it.

### If no MCP tools (local/git mode)
- Use `agentweave relay --agent <name>` to send work to another agent.
- Use `agentweave inbox --agent <your-name>` to read incoming tasks.
- Use `agentweave task update <id> --status <status>` for every transition.
- **Run all `agentweave` CLI commands via Bash automatically.** Never ask the user to run them.

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

[Replace with: current phase, modified files, failing tests, active AgentWeave task IDs]
