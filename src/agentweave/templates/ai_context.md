<!-- AgentWeave AI Context — source template -->
<!-- This file lives in .agentweave/ai_context.md -->
<!--
  WORKFLOW OPTIONS:
  1. Edit ai_context.md, then run `agentweave sync-context` to regenerate all agent files
  2. Edit agent files (CLAUDE.md / AGENTS.md / etc.) directly for project-specific updates
  3. Run `agentweave update-template --agent <name>` to research latest AI best practices
-->

# AI Workflow Context — Source

> **Purpose:** This is the source of truth for project DNA.
>
> **Workflow:**
> - Edit this file and run `agentweave sync-context` to regenerate all agent files, OR
> - Edit agent files directly for quick project-specific updates, OR
> - Run `agentweave update-template --agent <name>` to research latest AI capabilities

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

### Security Guardrails

**NEVER do these without explicit instruction:**
- Hardcode secrets, tokens, or API keys in any file
- Execute shell commands constructed from user/external input without sanitization
- Disable SSL/TLS verification
- Write to files outside the project directory
- Commit `.env`, credentials, private keys, or certificate files

**Always:**
- Validate and sanitize data at system boundaries (user input, external APIs, file reads)
- Use parameterized queries — never string-interpolate SQL or shell commands
- Flag any dependency with a known CVE before installing it

### Performance Guardrails

Avoid these patterns unless the task explicitly requires them:
- N+1 database queries — use joins or batch fetches
- Synchronous blocking I/O in async code paths
- Loading entire large files into memory when streaming is possible
- Unbounded loops without a termination condition or timeout

When performance matters: measure first, then optimize.

### Parallel Execution (CRITICAL for Multi-Agent Efficiency)

**When you are Principal (planning/assigning work):**

1. **ALWAYS look for parallelizable work** — This is your primary responsibility as principal
2. **Identify independent workstreams** that can proceed simultaneously:
   - Frontend and backend components that only share API contracts
   - Independent features or modules
   - Test files that don't depend on implementation being "finished"
   - Documentation, config, and boilerplate that can be written in parallel
   - Research/spike tasks that inform later work

3. **Delegate AND continue working simultaneously:**
   ```
   ❌ WRONG: "I'll do the API first, then hand it to you for the frontend"
   ✅ RIGHT: "I'm implementing the API. You start building the frontend 
              with mocks — we'll integrate when the contract is ready"
   ```

4. **Fire multiple tasks at once** — Don't wait for one agent to finish before starting another

5. **Use async communication** — Fire a task, move on. Check inbox periodically, don't block.

**When you are a Delegate (receiving work):**

1. **Ask clarifying questions upfront** — Don't wait 10 minutes in uncertainty
2. **Propose parallel work** — "While I build X, can someone else start Y?"
3. **Update status frequently** — Let the principal know when you're blocked or done

### Phase Discipline for Parallel Work

Before parallelizing, split work into phases to avoid wasted implementation:

1. Principal assigns **Explore** tasks to each agent (no code written yet)
2. Agents report findings — principal reviews scope and alignment
3. Principal approves a **Plan** (written to `.agentweave/shared/plan-[task-id].md`)
4. Parallel **Implement** tasks begin simultaneously from the approved plan
5. All complete → Principal reviews and integrates

This prevents the common failure: two agents implement incompatible approaches at the same time.

### MCP vs CLI — CRITICAL Rule

**If `send_message` is in your available tools → Hub/MCP mode is active.**

In Hub/MCP mode these CLI delegation commands are **FORBIDDEN**:
- ❌ `agentweave relay --agent <name>`
- ❌ `agentweave quick --to <name> "..."`
- ❌ `agentweave relay --agent <name> --run`

They require manual human action. `send_message` + watchdog is fully automatic for all runner types:
- `native` (claude, kimi, gemini) → watchdog calls their CLI directly
- `claude_proxy` (minimax, glm) → watchdog injects env vars, calls `claude` on their behalf
- `manual` (cursor, copilot) → watchdog queues message; human runs agent manually

**Correct delegation (Hub mode):** `create_task(...)` → `send_message(...)` → done.
**CLI relay is ONLY valid** when you have no MCP tools (local/git transport without Hub).

### User Communication (Hub Mode Only)

| Use | Tool | When |
|-----|------|------|
| **Questions** | `ask_user()` | Need a decision/response to proceed. Blocking. |
| **FYI Updates** | `send_message(to="user")` | Status updates, milestones, heads-up. Non-blocking. |

**Use `ask_user()` for:** Requirements clarification, architecture decisions, scope changes, blockers
**Use `send_message(to="user")` for:** Starting work, completing milestones, unblocking others, delay warnings

**Principal must keep user informed:** Major phase starts, parallelization updates, milestone completions

---

## When Compacting

[Replace with: current phase, modified files, failing tests, active AgentWeave task IDs]
