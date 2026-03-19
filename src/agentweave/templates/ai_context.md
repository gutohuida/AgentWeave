<!-- AgentWeave AI Context — source template -->
<!-- This file lives in .agentweave/ai_context.md and is NOT read by agents directly. -->
<!-- Edit the sections below, then run `agentweave update-template --agent <name>` -->
<!-- to regenerate CLAUDE.md / AGENTS.md / GEMINI.md at the project root. -->

# AI Workflow Context — Source

> **Purpose:** This is the source of truth for project DNA. Agents read their own
> auto-generated file (CLAUDE.md / AGENTS.md / GEMINI.md) at the project root instead.
>
> **To update agent files:** Edit this file, then run:
> `agentweave update-template --agent claude` (repeat for each agent in the session)

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

## When Compacting

[Replace with: current phase, modified files, failing tests, active AgentWeave task IDs]
