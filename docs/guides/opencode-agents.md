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

Apply changes:

```bash
agentweave activate
```

---

## MCP Setup

OpenCode uses a file-based MCP configuration (`opencode.json`) rather than a CLI `mcp add` command. AgentWeave handles this automatically:

```bash
agentweave mcp setup
```

This creates or updates `opencode.json` in your project root:

```json
{
  "mcp": {
    "agentweave": {
      "type": "local",
      "command": ["agentweave-mcp"]
    }
  }
}
```

If you already have an `opencode.json` with other configuration, AgentWeave merges only the `mcp.agentweave` key and preserves everything else.

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

The watchdog uses stable session IDs (`agentweave-{agent-name}`) so session continuity is maintained across pings without parsing streamed output.

### Via Switch Command

```bash
agentweave switch opencode-dev
```

This prints the ready-to-use launch command for the agent.

---

## Session Management

OpenCode agents use **stable session IDs** managed by AgentWeave:

- Format: `agentweave-{agent-name}` (e.g., `agentweave-opencode-dev`)
- Session IDs are pre-saved to `.agentweave/agents/{agent}-session.json`
- No output parsing is required — the session ID is deterministic

To start a fresh session, simply delete the agent's session file:

```bash
rm .agentweave/agents/opencode-dev-session.json
```

---

## Limitations

- **Tool-call reliability:** 7B local models may occasionally fail to invoke MCP tools correctly. If this happens, retry the task or use a larger model.
- **No stream parsing:** AgentWeave monitors only the exit code for OpenCode agents. Output is not streamed to the Hub in real-time.
- **No built-in context usage reporting:** Local models do not report token usage, so context monitoring is unavailable for OpenCode agents.

---

## See Also

- [Configuration Guide](../getting-started/configuration.md)
- [agentweave.yml Reference](../reference/agentweave-yml.md)
- [OpenCode Documentation](https://sst.dev)
- [Ollama Documentation](https://ollama.com)
