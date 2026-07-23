---
name: aw-setup
description: Guided end-to-end setup of this AgentWeave project — collaboration mode, Hub (none/local/remote), agents and runners, roles, security guardrails, and API keys. Use when setting up the project for the first time or reworking the whole configuration. For one concern at a time, use aw-setup-agent, aw-setup-hub, aw-setup-transport, aw-setup-roles, aw-setup-proxy, or aw-setup-security instead.
---

Walk the user through a complete AgentWeave project setup, one decision at a time. Do not batch all questions — ask, apply, move on.

**Project:** {project_name}
**Current mode:** {mode}
**Principal:** {principal}
**Current agents:** {agents_list}

## 1. Detect current state

Run these and read the results before asking anything:

1. `agentweave status` — is there a session? transport type? watchdog?
2. `agentweave doctor` — runtime readiness issues
3. Check which of these exist: `agentweave.yml`, `.agentweave/session.json`, `.agentweave/transport.json`, `.env`

If `agentweave.yml` doesn't exist yet, run:

```bash
agentweave init --project "<name>" --principal <principal-agent> --mode hierarchical
```

(`init` is fully flag-driven; it creates `.agentweave/`, a commented `agentweave.yml`, `.gitignore` entries, and a scaffold `.env`.)

If `agentweave.yml` already exists, check `project.scaffold` before deciding how to treat it:
- **`scaffold: true`** (or the file was just created by `init` above) — this is an untouched default, not a real decision. Run the **full interview** below as if nothing existed; don't skip questions just because the keys are present.
- **`scaffold` absent or `false`** — this file reflects reviewed answers. Read it and treat its values as the current answers — only ask the user what they want to change.

`scaffold: true` is cleared automatically the first time `agentweave activate` runs successfully (step 5), so a normal setup pass naturally flips it once the user is done.

## 2. Interview — one decision at a time

### a. Collaboration mode
- `hierarchical` — principal delegates and reviews (default, best for most teams)
- `peer` — agents coordinate as equals
- `review` — everything goes through review

Set via `project.mode` in `agentweave.yml`.

### b. Hub or no Hub?
- **No Hub** — single machine (local transport, the default) or cross-machine via git (`aw-setup-transport` covers both).
- **Local Hub** — web dashboard on this machine. Docker: `agentweave hub start`. No Docker: `agentweave hub start --native` (needs `pip install agentweave-hub`).
- **Remote Hub** — an existing Hub elsewhere: `agentweave transport setup --type http --url <url> --api-key <aw_live_...> --project-id <proj-...>`.

If a Hub is used, set `hub.url` in `agentweave.yml`. Details: invoke `aw-setup-hub`.

### c. Agents and runners
For each agent ask: name, runner, model, and whether it is the principal.

| Runner | Use for | Needs |
|---|---|---|
| `claude` | Claude Code CLI | `claude` on PATH |
| `kimi` | Kimi Code CLI | `kimi` on PATH |
| `codex` / `codex_mcp` | OpenAI Codex CLI | `codex` on PATH |
| `opencode` | opencode CLI | model as `provider/model` (case-sensitive) |
| `copilot` | GitHub Copilot CLI | `COPILOT_GITHUB_TOKEN` |
| `claude_proxy` | Minimax, GLM, or any Anthropic-compatible API through Claude Code | API key in `.env` — see `aw-setup-proxy` |
| `manual` | Cursor/Windsurf/web chat — human pastes relays | nothing |
| `native` | Anything else; AgentWeave spawns it generically | CLI path via `cli:` |

Rules enforced by config validation:
- Exactly **one** agent may have `principal: true`.
- Agent names must match `^[a-zA-Z0-9_-]{1,32}$`.
- `env:` is a list of environment variable **names**, never values.

Per-agent details: invoke `aw-setup-agent`.

### d. Roles per agent
Offer the catalog (full table in `aw-setup-roles`):

- Human-title: `tech_lead`, `architect`, `backend_dev`, `frontend_dev`, `fullstack_dev`, `qa_engineer`, `devops_engineer`, `security_engineer`, `data_engineer`, `ml_engineer`, `technical_writer`, `code_reviewer`, `project_manager`
- AI-native: `coordinator`, `model_router`, `explorer`, `implementer`, `verifier`, `guardian`, `context_keeper`

Sensible defaults: principal → `tech_lead` (hierarchical) or `coordinator` (peer); a second strong agent → `code_reviewer` or `verifier`. Set via `agents.<name>.roles` in the yml or `agentweave roles set <agent> <csv>`.

### e. Security guardrails
Ask about each `quality:` option (details in `aw-setup-security`):
- `review_required: true` — force review before tasks complete?
- `echo_chamber_guard: off|warn|enforce` — block self-review (recommend at least `warn`)
- `dependency_check: true` — flag hallucinated package names (slopsquatting)
- `attribution_tag: true` — audit trail on completed tasks
- If any guard is enforced, suggest assigning the `guardian` or `security_engineer` role.

### f. API keys
From the chosen runners, list every required key (`MINIMAX_API_KEY`, `ZHIPU_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CODEX_API_KEY`, `COPILOT_GITHUB_TOKEN`, …). Keys go in the project-root `.env` (gitignored, auto-loaded) — **never** in `agentweave.yml`. Check which are already present in `.env` or the shell environment; prompt the user to add the missing ones.

## 3. Write the configuration

Edit `agentweave.yml` with everything decided above. Skeleton:

```yaml
project:
  name: "{project_name}"
  mode: hierarchical        # hierarchical | peer | review

hub:
  url: http://localhost:8000   # only when using a Hub

agents:
  {principal}:
    runner: claude
    principal: true
    roles: [tech_lead]
  kimi:
    runner: kimi
    roles: [backend_dev]

quality:
  review_required: true
  echo_chamber_guard: warn    # off | warn | enforce
  dependency_check: true
  attribution_tag: true
```

## 4. Hub / transport

- Local Hub chosen: `agentweave hub start` — note the `aw_live_...` API key it prints (saved in `~/.agentweave/hub/.env`).
- Remote Hub: run the `transport setup --type http ...` command from 2b.
- No Hub, cross-machine: `agentweave transport setup --type git` (see `aw-setup-transport`).
- Single machine: nothing to do — local transport is the default.

## 5. Activate and verify

```bash
agentweave activate     # reconcile agentweave.yml -> runtime (agents, transport, MCP, watchdog)
agentweave doctor       # fix anything it reports
agentweave status       # confirm agents, transport, watchdog
agentweave agents list  # confirm roster and roles
```

`activate` auto-fetches the Hub API key when `hub.url` is set, so manual `transport setup` is usually unnecessary for a local Hub.

## 6. Wrap up

Print a summary: mode, agents + runners + roles, transport/Hub, security guards, missing API keys (if any), and the next steps — fill in `.agentweave/ai_context.md`, then start the principal agent.

For incremental changes later, point the user to the specialized skills: `aw-setup-agent`, `aw-setup-hub`, `aw-setup-transport`, `aw-setup-roles`, `aw-setup-proxy`, `aw-setup-security`.
