# OpenCode Agents

[OpenCode](https://sst.dev) is a terminal-based AI coding agent that supports 75+ providers including local Ollama models. AgentWeave integrates OpenCode as a first-class runner, giving you a zero-cost delegate tier for tasks like test generation, boilerplate, and targeted refactoring.

---

## Installation

OpenCode is a user-installed CLI (not a Python dependency):

```bash
npm install -g opencode
```

Verify installation:

```bash
opencode --version
```

### Local Model Setup (Ollama)

For zero-cost local inference:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a coding-capable model
ollama pull qwen2.5-coder:7b
```

> **Note:** Small local models (7B) may have inconsistent tool-call behavior. Qwen2.5-Coder:7b is the minimum viable local model for reliable MCP tool use.

---

## Configuration

Add an OpenCode agent to `agentweave.yml`:

```yaml
agents:
  opencode-dev:
    runner: opencode
    model: ollama/qwen2.5-coder:7b
    roles:
      - backend_dev

  opencode-qa:
    runner: opencode
    model: anthropic/claude-sonnet-4-5
    roles:
      - qa_engineer
```

The `model` field accepts any OpenCode-supported provider/model string:

- Local: `ollama/qwen2.5-coder:7b`, `ollama/llama3.2`
- Cloud: `anthropic/claude-sonnet-4-5`, `openai/gpt-4o`, etc.
- Omit `model` entirely to use OpenCode's default

See [Switching opencode Models](opencode-models.md) for how to change the model, set up auth with a new provider, or troubleshoot `ProviderModelNotFoundError` errors.

### Pinning the `opencode` binary (WSL / multi-install hosts)

When more than one `opencode` is on `PATH` — very common on WSL hosts that
have both a Linux install (e.g. `~/.opencode/bin/opencode`) and a Windows
install on the npm global path (e.g.
`/mnt/c/Users/<you>/AppData/Roaming/npm/opencode`) — the watchdog picks
whichever `shutil.which` resolves first. Older binaries don't know about
newer providers or models, so a perfectly valid `model:` value can return
`ProviderModelNotFoundError` from opencode.

Pin the binary explicitly per agent with `cli:`:

```yaml
agents:
  opencode:
    runner: opencode
    model: minimax-coding-plan/MiniMax-M3
    cli: /mnt/c/Users/you/AppData/Roaming/npm/opencode
```

When `cli:` is set, the watchdog:

- Skips `shutil.which` and invokes that exact path.
- Verifies the file is executable at launch time and surfaces a clear
  `agent_cli_missing` diagnostic if it isn't.
- Renders the same pinned path in `agentweave switch` and
  `agentweave activate` so the human-run command matches the watchdog.

When `cli:` is omitted, the watchdog falls back to `shutil.which("opencode")`
as before — fully backwards compatible.

Verify what the watchdog will pick up with:

```bash
which opencode
opencode --version
```

If the first `opencode` on PATH is older than the binary that
actually has your provider, either reorder PATH or use the `cli:`
override.

Apply changes:

```bash
agentweave activate
```

---

## AgentWeave access path

OpenCode currently uses the Hub command path. The turn prompt supplies queued input and tells the
agent to use ordinary `agentweave` commands for outbound collaboration. No `opencode.json` MCP block
or global client setup is required; provider/model configuration remains unchanged.

---

## Running an OpenCode Agent

### Manual Launch

```bash
# With a specific model
opencode run --model ollama/qwen2.5-coder:7b --session agentweave-opencode-dev --format json "Check your inbox and respond to any messages"

# With context file injection (auto-injected by watchdog)
opencode run --session agentweave-opencode-dev --file .agentweave/context/opencode-dev.md --format json "Implement the auth module"
```

### Via Watchdog Auto-Ping

Once configured, the AgentWeave watchdog automatically pings OpenCode agents when messages or tasks arrive:

```bash
agentweave start
```

The watchdog reads OpenCode's JSON event stream, stores the real session ID returned by the first
run, and passes that ID to later invocations so continuity is maintained across pings.

### Via Switch Command

```bash
agentweave switch opencode-dev
```

This prints the ready-to-use launch command for the agent.

---

## Session Management

OpenCode agents use provider session IDs managed by AgentWeave:

- New runs use a stable AgentWeave title such as `agentweave-opencode-dev`.
- AgentWeave captures OpenCode's returned `sessionID`.
- The ID is saved to `.agentweave/agents/{agent}-session.json` and passed with `--session` later.

To start a fresh session, simply delete the agent's session file:

```bash
rm .agentweave/agents/opencode-dev-session.json
```

---

## Limitations

- **Tool-call reliability:** 7B local models may occasionally fail to invoke MCP tools correctly. If this happens, retry the task or use a larger model.
- **Provider metadata varies:** If the active model catalog exposes no input or context limit,
  AgentWeave shows a token-only context sample instead of guessing a percentage.
- **Reasoning accounting:** OpenCode reports reasoning separately; AgentWeave subtracts it from
  `total` when calculating the effective context observation.

---

## See Also

- [Configuration Guide](../getting-started/configuration.md)
- [agentweave.yml Reference](../reference/agentweave-yml.md)
- [OpenCode Documentation](https://sst.dev)
- [Ollama Documentation](https://ollama.com)
- [Agent stream and context contracts](../reference/agent-stream-contract.md)
