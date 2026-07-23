---
name: aw-setup-agent
description: Add a new agent or reconfigure an existing one in agentweave.yml — runner choice (claude, kimi, codex, opencode, copilot, claude_proxy, manual, native), model, roles, env vars, yolo/pilot. Use whenever the agent roster changes. For full project setup use aw-setup; for claude_proxy specifics use aw-setup-proxy.
---

Add or reconfigure a single agent in this AgentWeave project.

**Project:** {project_name} — **current agents:** {agents_list} (principal: {principal})

## 1. Gather the facts

Ask (or infer from the request):

- **Name** — must match `^[a-zA-Z0-9_-]{1,32}$` (e.g. `kimi`, `minimax`, `review-bot`).
- **Runner** — how AgentWeave launches it:

| Runner | CLI used | Notes |
|---|---|---|
| `claude` | `claude` | Claude Code |
| `kimi` | `kimi` | Kimi Code |
| `codex` | `codex` | OpenAI Codex CLI |
| `codex_mcp` | `codex` | Codex via MCP |
| `opencode` | `opencode` | `model` must be `provider/model`, case-sensitive |
| `copilot` | `copilot` | needs `COPILOT_GITHUB_TOKEN` |
| `claude_proxy` | `claude` | Minimax/GLM/custom API through Claude Code — see `aw-setup-proxy` |
| `manual` | — | human relays prompts (Cursor, Windsurf, web chat) |
| `native` | any | generic spawn; pin binary with `cli:` |

- **Model** — always ask which model to use, even when the runner has a built-in default (e.g. `claude_proxy` providers). Passed to the CLI when supported.
- **Roles** — pick from `agentweave roles available` (or invoke `aw-setup-roles`).
- **yolo** — auto-approve all tool prompts (autonomous loops only).
- **pilot** — human drives the CLI session manually; auto-execution is disabled.
- **env** — list of environment variable **names** the runner needs (e.g. `[MINIMAX_API_KEY]`). Values live in `.env`, never in the yml.

## 2. Edit agentweave.yml

Add or update the agent block:

```yaml
agents:
  <name>:
    runner: <runner>          # required
    model: <model>            # optional
    roles: [backend_dev]      # from the role catalog
    env: [SOME_API_KEY]       # variable NAMES, not values
    yolo: false
    pilot: false
    # principal: true         # at most ONE agent may be principal
    # base_url: https://...   # claude_proxy custom endpoint (must be http/https)
    # cli: /abs/path/to/cli   # pin a binary (e.g. WSL with several opencode installs)
    # runner_options:         # free-form map passed to the runner
    #   memory: false
```

Validation rules that will reject the file:
- More than one `principal: true` across agents.
- `env:` written as a mapping or containing values — it must be a list of names.
- `base_url` not starting with `http://` / `https://`.
- Unknown `runner` — must be one of: `claude`, `native`, `claude_proxy`, `kimi`, `manual`, `opencode`, `codex`, `codex_mcp`, `copilot`.

Shortcut for claude_proxy agents (writes the same runtime state without editing the yml by hand):

```bash
agentweave agent configure <name> --runner claude_proxy --api-key-var MINIMAX_API_KEY
```

Other useful commands:

```bash
agentweave agent set-model <name> <model>     # change model later
agentweave agent configure <name> --pilot     # toggle pilot mode
```

## 3. Apply and verify

```bash
agentweave activate       # reconcile yml -> runtime state
agentweave agents list    # confirm the agent appears with the right runner/roles
agentweave doctor         # catch missing CLIs, keys, or MCP issues
```

If the agent needs an API key, remind the user to add it to the project-root `.env` (gitignored, auto-loaded by the CLI and watchdog).
