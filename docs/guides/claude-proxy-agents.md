# Claude-Proxy Agents

Some models — like **MiniMax** and **Zhipu GLM** — don't have a native CLI. AgentWeave runs them through the Claude Code CLI by overriding two environment variables:

```
ANTHROPIC_BASE_URL  →  the provider's OpenAI-compatible endpoint
ANTHROPIC_API_KEY   →  the provider's API key (resolved from your shell at runtime)
```

This is called a **`claude_proxy` runner**. AgentWeave tracks a separate Claude resume session ID per proxy agent so each one maintains its own conversation history.

## Setup

### Built-in Providers

```bash
# Initialize with a proxy agent
agentweave init --project "My App" --agents claude,minimax

# Configure using built-in defaults
agentweave agent configure minimax
agentweave agent configure glm
```

### Custom Provider

```bash
agentweave agent configure mymodel \
  --runner claude_proxy \
  --base-url https://api.example.com/v1 \
  --api-key-var MY_MODEL_API_KEY
```

## Running a Proxy Agent

### Option A — Manual Switch

Switch env vars in your current shell, then run Claude manually:

```bash
export MINIMAX_API_KEY=<your-key>
eval $(agentweave switch minimax)          # exports ANTHROPIC_BASE_URL + ANTHROPIC_API_KEY
claude --resume <session-id> -p "..."
```

### Option B — Auto-Run

Let AgentWeave handle it (sets env + launches Claude with relay prompt):

```bash
export MINIMAX_API_KEY=<your-key>
agentweave run --agent minimax
```

### Option C — From Relay

```bash
agentweave relay --agent minimax           # shows copy-paste prompt + switching instructions
agentweave relay --agent minimax --run     # combined: sets env + launches Claude
```

## Session Continuity

AgentWeave tracks the Claude session ID per proxy agent so `--resume` is used automatically on subsequent runs. To register a session ID manually:

```bash
agentweave agent set-session minimax <session-id>
```

## Built-in Provider Registry

| Agent | Base URL | Env var |
|-------|----------|---------|
| `minimax` | `https://api.minimax.chat/v1` | `MINIMAX_API_KEY` |
| `glm` | `https://open.bigmodel.cn/api/paas/v4` | `ZHIPU_API_KEY` |

## Security Note

API keys are **never stored** in `session.json`. Only the env var *name* is stored (e.g. `MINIMAX_API_KEY`). The actual value is resolved from your shell at runtime.

## See Also

- [Configuration](../getting-started/configuration.md) — general AgentWeave configuration
- [CLI Commands Reference](../reference/cli-commands.md) — `agentweave agent configure`, `agentweave run`, `agentweave switch`
