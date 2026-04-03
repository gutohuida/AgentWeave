<!-- {version} — auto-generated from .agentweave/ai_context.md -->
<!-- You MAY edit this file directly for project-specific updates. -->
<!-- To regenerate from ai_context.md, run: agentweave sync-context --agent kimi -->
<!-- To update with latest AI best practices, run: agentweave update-template --agent kimi -->

> **Token-saving note:** Do NOT read `.agentweave/ai_context.md` — this file already contains all necessary project context. Reading it again wastes tokens.

# AI Workflow Context

## Session Start Checklist (REQUIRED)

**Before doing ANY work, complete these steps in order:**

1. **Load your role** — follow the steps in the **Your Role** section below.
2. **Read `.agentweave/protocol.md`** — learn the collaboration protocol and who the other agents are.
3. **Read `.agentweave/shared/context.md`** — see current focus and recent decisions.
4. **Check for AgentWeave MCP tools** — look for `send_message`, `get_inbox`, `update_task`, `ask_user` in your available tools.
   - If MCP tools are available → use them exclusively for all coordination.
   - If no MCP tools → use `agentweave relay` / `agentweave inbox` CLI commands.
5. **Run `agentweave status`** — see all pending tasks before starting any work.
6. **Check for a prior checkpoint** — look for `.agentweave/shared/checkpoints/{your_name}-*.md`. If one exists, read the most recent file. Your "Next Steps" from the last session is your starting point.

**Do NOT skip this checklist.** An agent that begins work without knowing its role has no valid scope and must stop and complete the checklist.

---

## Your Role

Your role config is at `.agentweave/roles.json`.

**On each session start:**

1. Read `.agentweave/roles.json` — find `agent_assignments.<your_name>` to get your role key,
   then note `roles.<role_key>.version`.
2. **If you already know this role key + version** from this conversation: skip to step 4.
3. **If new or version changed:** read the file at `roles.<role_key>.file`
   (e.g. `.agentweave/roles/backend_dev.md`) in full.
   Say to yourself: *"I am <your_name>, assigned <role_key> v<version>."*
4. **Do NOT read other agents' role files** — only yours.

This is your ONLY responsibility this session. Your role file defines what you own and what you must not do.

---

## Role Adherence Rules

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

### Proactive Delegates (When You Are NOT Principal)

Even as a delegate, you can suggest parallel work:

- **Propose parallel tasks** — "While I implement X, can someone work on Y?"
- **Identify blockers early** — Don't wait hours; ask immediately if unclear
- **Suggest splits** — "This task has 3 independent parts, suggest we parallelize"
- **Complete and immediately ask** — "Done with X. Is there parallel work I can take?"

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
- Disable SSL/TLS verification (`verify=False`, `InsecureRequestWarning`, etc.)
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

When performance matters: measure first (`time`, `cProfile`, profiler of your stack), then optimize.

---

## Multi-Agent Workflow

**Always check for AgentWeave MCP tools at session start** (`send_message`, `get_inbox`, `update_task`, `ask_user`). Then:

### ⚠ CRITICAL: MCP vs CLI — Pick One, Never Mix

**If `send_message` is in your available tools → you are in Hub/MCP mode.**

In Hub/MCP mode, the following CLI commands are **FORBIDDEN** for agent delegation:
- ❌ `agentweave relay --agent <name>`
- ❌ `agentweave quick --to <name> "..."`
- ❌ `agentweave relay --agent <name> --run`

These generate relay prompts that require **manual human action**. In Hub mode, the watchdog auto-pings agents the moment `send_message` is called — no human intervention needed.

**The watchdog handles ALL agent runner types automatically:**
- `native` (claude, kimi, gemini) — calls their CLI directly
- `claude_proxy` (minimax, glm) — injects env vars and calls `claude` CLI on their behalf
- `manual` (cursor, copilot) — queues the message; human runs agent manually

**Correct delegation in Hub/MCP mode:**
```
1. create_task(title="...", assignee="another_agent", assigner="{your_name}", ...)
2. send_message(from_agent="{your_name}", to_agent="another_agent",
               subject="New task: ...", content="...",
               message_type="delegation", task_id="<id>")
   → watchdog fires automatically, no relay, no user action needed
```

### If MCP tools are available (Hub mode)
- Use `send_message` to route work to other agents — NEVER use CLI relay commands.
- Use `get_inbox` to read incoming tasks and messages.
- Use `update_task` for every status transition.
- Use `ask_user` when a decision requires human input — do not interrupt with direct chat.
- NEVER report task status directly to the user when another agent should receive it.

### Parallel Execution (When You Are Principal)

**Your goal:** Keep ALL agents busy with independent workstreams. Linear = failure.

**Planning Phase — Look for these parallel splits:**
| Situation | Parallel Work Distribution |
|-----------|---------------------------|
| API + Frontend | You: API implementation → Another agent: Frontend with mocks → Integrate when API ready |
| Feature + Tests | You: Core implementation → Another agent: Test scaffolding + edge cases |
| Multiple endpoints | You: Auth endpoints → Another agent: CRUD endpoints → Someone: Integration tests |
| Refactor + Feature | You: Refactor existing code → Another agent: New feature using stable API |
| Research + Build | You: Build with assumptions → Another agent: Research to validate assumptions |

**Execution Pattern:**
1. Create YOUR task first (so you don't become a manager-only)
2. Identify 1-3 parallel tasks for other agents
3. Fire all tasks simultaneously via `create_task`
4. Work on YOUR task while others work on theirs
5. Check inbox every 10-15 minutes, not continuously

**Anti-Patterns (NEVER do this):**
- ❌ "I'll build the foundation first, then assign work"
- ❌ Sequential handoffs: A → B → C → D
- ❌ One agent waiting for another to finish
- ❌ Principal only managing, not coding

### Phase Discipline

Always respect the phase specified in the delegated task:
- **Explore** — read files, run read-only commands, produce a findings report. Do NOT modify files.
- **Plan** — produce a step-by-step plan. Do NOT write code. Await principal approval before implementing.
- **Implement** — execute an approved plan. Run tests/lint before marking done.
- **Verify** — confirm work using the verification commands specified in the task.

If no phase is specified, default to: **Explore → share findings → await Plan approval → Implement**.

### If no MCP tools (local/git mode — relay is the ONLY valid context for these commands)
- Use `agentweave relay --agent <name>` to send work to another agent.
- Use `agentweave inbox --agent <your-name>` to read incoming tasks.
- Use `agentweave task update <id> --status <status>` for every transition.
- **Run all `agentweave` CLI commands via Bash automatically.** Never ask the user to run them.

### A2A Communication Standard (all agent-to-agent messages)

**Rule: structured fields, no prose.** Agents receiving a message need data, not explanation.

All `send_message()` calls between agents MUST use this format in the `content` field:

```
COMPLETED:    <deliverables — file paths, names, IDs>
CONTEXT:      <decisions and constraints — 1 line each>
REMAINING:    <exact next action for recipient — imperative, specific>
CONSTRAINTS:  <what recipient must not do — omit entirely if none>
VERIFICATION: <runnable command>
```

Message length budgets:
- Delegation: 10 lines max — Completion: 8 lines max — Blocker/question: 5 lines max

**Never write preamble** ("I've finished..."), **never write postamble** ("Let me know if you need help").
Write A2A messages like a function call, not an email.
Use natural language ONLY for `ask_user()` and `send_message(to="user")`.

---

### User Communication (Hub Mode Only)

Distinguish between questions that need answers and informational updates:

| Use | Tool | When |
|-----|------|------|
| **Questions** | `ask_user()` | You need a decision, clarification, or response to proceed. Blocks work until answered. |
| **FYI Updates** | `send_message(to="user")` | Status updates, important findings, blockers resolved, milestones reached. No response needed. |

**When to Use `ask_user()` (Questions Tab):**
- Clarifying requirements that affect implementation approach
- Architecture decisions with trade-offs ("Option A or B?")
- Scope changes ("This is bigger than estimated, should we split it?")
- Blocking issues you can't resolve yourself

**When to Use `send_message(to="user")` (Messages Tab):**
- Starting a significant task ("Beginning the auth refactor now")
- Completed a milestone ("Database schema deployed, tests passing")
- Found an issue but have a solution ("Discovered race condition, fixing with mutex")
- Unblocking others ("Fixed the API bug another agent was waiting on")

**Principal's Duty: Keep the User Informed**
- Send a message at the start of major phases
- Notify when work is parallelized ("Another agent is building backend while I do frontend")
- Report completion of significant milestones
- Warn early about blockers or delays ("Running 30min behind due to X")

### Escalation Path (when to stop and ask)

| Situation | Action |
|-----------|--------|
| Missing info needed to proceed | `ask_user` (Hub) or message principal |
| Task scope is larger than expected | Stop, report findings, await revised task |
| Conflict between task and its constraints | Stop — do NOT proceed unilaterally |
| Uncertain which files are safe to modify | Ask before touching anything |
| Tests fail after implementation | Fix or report — never mark `completed` with failing tests |
| Blocked for more than a few minutes | Escalate immediately — do not silently stall |

---

## Sub-Agent Setup

Create these in `.agentweave/subagents/` based on project type. Each agent outputs findings
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

## Context Checkpoint Protocol

**Never compact without writing a checkpoint first.**

### When to checkpoint — act at ALL of these triggers

- About to clear context
- Completed a phase (Explore done, Plan approved, Implement complete)
- About to hand off work to another agent
- About to end session / go idle
- Modified 5+ files since last checkpoint
- Struggling to recall decisions made earlier in the session

### How to checkpoint

**Option A — MCP tool (preferred):**
Call `save_checkpoint(agent="{your_name}", session_intent="...", files_modified=[...], decisions=[...], next_steps=[...], reason="<reason>")`.

**Option B — CLI:**
Run `agentweave checkpoint --agent {your_name} --reason <reason>`, then fill in the generated skeleton at `.agentweave/shared/checkpoints/`.

**Option C — Write manually:**
Create `.agentweave/shared/checkpoints/{your_name}-<timestamp>.md` with these sections:

```markdown
# Context Checkpoint — {your_name} — <datetime>

## Session Intent
One paragraph: what was this session trying to accomplish.

## Active Tasks at Checkpoint
| Task ID | Title | Status |

## Files Modified This Session
- `path/to/file` — what changed

## Decisions Made
1. [Decision] — [why — this is the critical part; the code exists, the rationale does not]

## Blockers and Open Questions
- [ ] unresolved item

## Next Steps
1. Exact first action after resuming

## Verification Commands
```bash
pytest tests/
```
---
Reason: token_threshold | phase_complete | pre_handoff | pre_sleep | manual
```

### After writing a checkpoint

1. Clear your context
2. Immediately re-read your checkpoint file
3. Re-read `.agentweave/shared/context.md`
4. Resume from "Next Steps" in the checkpoint

### Context thresholds by model

| Model | Compact at |
|-------|-----------|
| You | 55–60% context fill |
| Claude | 40–50% |
| GLM | 60–65% |
| Minimax | built-in at 30% |

If the watchdog or Hub UI signals a `context_warning`, write a checkpoint immediately.
