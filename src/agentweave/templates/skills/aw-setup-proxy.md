---
name: aw-setup-proxy
description: Set up claude_proxy agents — run Minimax, GLM, or any Anthropic-compatible model through the Claude Code CLI. Covers built-in providers, custom endpoints, API keys in .env, switch/run usage. Use when adding or debugging a proxy agent. For full project setup use aw-setup.
---

Set up a claude_proxy agent: an external model served through the Claude Code CLI by pointing it at an Anthropic-compatible endpoint.

**Project:** {project_name} — **agents:** {agents_list}

## 1. Built-in providers

| Provider | Base URL | API key var | Default model |
|---|---|---|---|
| `minimax` | `https://api.minimax.io/anthropic` | `MINIMAX_API_KEY` | `MiniMax-M2.7` |
| `glm` | `https://open.bigmodel.cn/api/anthropic` | `ZHIPU_API_KEY` | `glm-5` |

Naming an agent `minimax` or `glm` auto-selects `claude_proxy` as its runner with these defaults.

## 2. Configure the agent

Quick path (updates runtime state directly):

```bash
agentweave agent configure minimax --runner claude_proxy --api-key-var MINIMAX_API_KEY
agentweave agent configure glm --runner claude_proxy --api-key-var ZHIPU_API_KEY
```

Custom provider (any Anthropic-compatible endpoint):

```bash
agentweave agent configure <name> --runner claude_proxy \
  --base-url https://your-endpoint.example/anthropic \
  --api-key-var YOUR_API_KEY \
  --model your-model-name
```

Declarative alternative — in `agentweave.yml`:

```yaml
agents:
  minimax:
    runner: claude_proxy
    model: MiniMax-M2.7        # optional, defaults per provider
    env: [MINIMAX_API_KEY]     # variable NAMES, not values
    roles: [backend_dev]
```

then `agentweave activate`.

## 3. Put the API key in .env

Add the key to the project-root `.env` (created by `agentweave init`, gitignored, auto-loaded by the CLI and the watchdog):

```
MINIMAX_API_KEY=<your-key>
```

Never put the key value in `agentweave.yml` or any committed file.

## 4. Use the proxy agent

Interactive shell — export the endpoint and key into your current shell:

```bash
eval $(agentweave switch minimax)
claude    # now talks to the proxy provider
```

One-shot run with automatic delegation env:

```bash
agentweave run --agent minimax "implement the login endpoint"
```

Change the model later:

```bash
agentweave agent set-model minimax MiniMax-M2.5
```

## 5. Verify

```bash
agentweave agents list     # runner shows claude_proxy, correct model
agentweave doctor          # CLI present, key resolvable
```

Troubleshooting:
- **Auth errors** — key missing from `.env` and the shell env; both are checked.
- **Wrong endpoint** — re-run `agent configure ... --base-url ...`; check `eval $(agentweave switch <name>)` output for `ANTHROPIC_BASE_URL`.
- **Model rejected** — provider model names are case-sensitive; use `agent set-model` with the exact ID.
