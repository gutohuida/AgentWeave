## Why

Setting up AgentWeave requires too many steps and commands to memorize before collaboration can begin — Hub bootstrap alone takes five sub-steps, and every agent configuration change requires a separate imperative command. This friction discourages adoption and makes it hard to return to a project after time away.

## What Changes

- **New**: `agentweave hub start/stop/status` commands manage the Hub Docker lifecycle from the CLI — no manual curl, .env editing, or docker compose commands needed
- **New**: Hub auto-generates its own API key on first startup and exposes it on a localhost-only endpoint; the CLI fetches it automatically
- **New**: `agentweave activate` — single command that connects to the Hub, sets up MCP, and starts the watchdog (replaces `transport setup` + `mcp setup` + `start`)
- **New**: `agentweave.yml` declarative config file at project root — defines project settings, Hub connection, agents (runner/model/roles/env/yolo/pilot), and optional scheduled jobs
- **Modified**: `agentweave init` no longer accepts `--agents` flag; creates `agentweave.yml` with only the principal agent defined
- **Modified**: `agentweave activate` reads `agentweave.yml` and reconciles all configuration state (session.json, transport.json, MCP registration) — idempotent, safe to re-run
- **Removed**: Need to call `transport setup`, `mcp setup`, `roles add/set/remove`, `agent configure`, `agent set-model`, `yolo`, `jobs create/pause/resume` as separate commands (all covered by editing `agentweave.yml` + `agentweave activate`)

## Capabilities

### New Capabilities

- `hub-lifecycle`: CLI management of Hub Docker container — start, stop, status, auto-key generation and discovery
- `activate-command`: Single idempotent command that applies `agentweave.yml` to the full runtime state (transport, MCP, watchdog, session agents)
- `declarative-config`: `agentweave.yml` as the single source of truth for project config, agent definitions, and scheduled jobs

### Modified Capabilities

- `agent-init`: `agentweave init` no longer takes `--agents`; produces `agentweave.yml` instead of writing agents directly into session.json

## Impact

- `src/agentweave/cli.py` — new `cmd_hub_*` functions, new `cmd_activate`, modified `cmd_init`, new YAML parsing logic
- `src/agentweave/session.py` — new `add_agent` / `sync_agents` methods to support hot-adding agents from YAML
- `hub/hub/main.py` — new `/setup/token` endpoint (localhost-only) for key discovery
- `hub/docker-compose.yml` — Hub generates key on first start if none set
- `agentweave.yml` — new file created at project root by `agentweave init`
- No changes to operational commands: `start`, `stop`, `task`, `msg`, `relay`, `quick`, `delegate`, `checkpoint`, `status`, `log`, `session register`
