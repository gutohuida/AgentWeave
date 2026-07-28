## Why

Cloud AI coding agents (Claude, Kimi) are expensive per-token, and many tasks — test generation, boilerplate, targeted refactoring — don't require frontier-model reasoning. OpenCode is a terminal-based AI coding agent that supports 75+ providers including local Ollama models, giving AgentWeave users a zero-cost delegate tier that participates as a full collaboration citizen.

## What Changes

- Add `"opencode"` as a valid runner type in `agentweave.yml` alongside `claude`, `kimi`, `claude_proxy`, and `manual`
- Users can configure named OpenCode agents (e.g. `opencode-dev`, `opencode-qa`) with any provider/model string (e.g. `ollama/qwen2.5-coder:7b`, `anthropic/claude-sonnet-4-5`)
- `agentweave mcp-setup` gains a file-based registration path that writes AgentWeave's MCP server into `opencode.json` (OpenCode has no `mcp add` CLI command)
- The watchdog gains an `opencode` dispatch branch that builds `opencode run [--model] [--session] [--file] --format json` commands
- Session continuity is handled via stable predictable IDs (`agentweave-{agent}`) rather than parsing streamed output
- Role guides and agent context files are injected via `--file` flags at invocation time
- OpenCode agents are full MCP clients: they can call `get_inbox`, `update_task`, `send_message`, and all other AgentWeave MCP tools autonomously

## Capabilities

### New Capabilities

- `opencode-runner`: The runner type definition, dispatch logic, MCP registration, and session management for OpenCode agents
- `opencode-config`: The agentweave.yml schema support and validation for `runner: opencode` with `model: provider/model`

### Modified Capabilities

<!-- No existing spec-level requirement changes -->

## Impact

- `src/agentweave/constants.py` — `RUNNER_TYPES`, `RUNNER_CONFIGS`, `AGENT_RUNNER_DEFAULTS`
- `src/agentweave/watchdog.py` — `_agent_ping_cmd()` dispatch
- `src/agentweave/cli.py` — `cmd_mcp_setup()` file-based registration path
- `src/agentweave/config.py` — `RUNNER_TYPES` validation already imports from constants; no structural changes needed
- New file: `opencode.json` written to project root by `agentweave mcp-setup`
- New dependency: `opencode` CLI must be installed by the user (not a Python package dependency)
- `tests/test_cli.py`, `tests/test_watchdog.py` — new test cases for opencode runner
