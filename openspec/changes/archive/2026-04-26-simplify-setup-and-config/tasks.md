## 1. Hub Auto-Key Generation (Hub side)

- [x] 1.1 Add startup logic in `hub/hub/main.py` to auto-generate `aw_live_<random32>` if `AW_BOOTSTRAP_API_KEY` is unset or matches the `.env.example` placeholder
- [x] 1.2 Store the auto-generated key in the database on first run (reuse existing API key model)
- [x] 1.3 Add `GET /setup/token` endpoint in Hub that returns `{ "api_key": "..." }` — restrict to `127.0.0.1` only using middleware
- [x] 1.4 Update `hub/.env.example` to make `AW_BOOTSTRAP_API_KEY` optional (document auto-generation behavior)
- [x] 1.5 Add tests for auto-key generation and `/setup/token` endpoint (localhost-only restriction)

## 2. `agentweave hub` Commands (CLI side)

- [x] 2.1 Add `cmd_hub_start()` in `cli.py`: download `docker-compose.yml` + `.env` to `~/.agentweave/hub/` if not present, run `docker compose up -d`, poll `/health` up to 30s, print Hub URL
- [x] 2.2 Add `cmd_hub_stop()` in `cli.py`: run `docker compose down` from `~/.agentweave/hub/`, handle not-running case gracefully
- [x] 2.3 Add `cmd_hub_status()` in `cli.py`: check Hub health endpoint, print running/stopped status and URL
- [x] 2.4 Add `hub` subparser with `start`, `stop`, `status` sub-commands in `create_parser()`
- [x] 2.5 Add routing branches for `hub_command` in `main()`
- [x] 2.6 Add helper to detect if Docker is available; print clear error if not
- [x] 2.7 Add tests for `agentweave hub start/stop/status` CLI commands

## 3. `agentweave.yml` Config File

- [x] 3.1 Create `src/agentweave/config.py` with `load_agentweave_yml()` and `AgentWeaveConfig` dataclass covering `project`, `hub`, `agents`, and `jobs` sections
- [x] 3.2 Implement YAML validation: reject `env:` as key-value dict (must be list of strings), validate runner values, validate cron expressions in jobs, report line numbers on parse errors
- [x] 3.3 Write `generate_agentweave_yml(session)` utility that serializes an existing `Session` object into `agentweave.yml` format (used by migration path in `cmd_init`)
- [x] 3.4 Add `agentweave.yml` to `.gitignore` exception list docs (it SHOULD be committed); add `.env` gitignore guidance in generated file header comment

## 4. Modified `agentweave init`

- [x] 4.1 Remove `--agents` as a required flag; make it optional with a deprecation warning when used
- [x] 4.2 Update `cmd_init()` to create `agentweave.yml` in the project root after session creation
- [x] 4.3 Add migration path: if `.agentweave/session.json` already exists when `init` runs, generate `agentweave.yml` from existing session instead of overwriting it
- [x] 4.4 Update `cmd_init()` tests to cover no-agents case and migration case
- [x] 4.5 Update CLI help text and README quickstart to reflect new init behavior

## 5. `agentweave activate` Command

- [x] 5.1 Add `cmd_activate()` in `cli.py` — entry point that orchestrates all reconciliation steps in order
- [x] 5.2 Implement transport step: if no `transport.json`, call `GET <hub.url>/setup/token`, write `transport.json`; if exists with same URL, skip
- [x] 5.3 Implement agent sync step: read `agents:` from `agentweave.yml`, call `session.sync_agents(declared_agents)` — add new, update existing, print notice for orphaned agents
- [x] 5.4 Add `sync_agents(declared: dict)` method to `Session` class in `session.py` that applies agent config (runner, model, roles, env_vars, yolo, pilot) and saves
- [x] 5.5 Implement MCP step: check if MCP already registered; if not, run `cmd_mcp_setup` logic; print skip message if already done
- [x] 5.6 Implement watchdog step: check watchdog PID; if not running, start it; print skip message if already running
- [x] 5.7 Implement jobs sync step: if `jobs:` section present, create/update jobs on Hub via HTTP transport; respect `enabled` field for pause/resume; skip entirely if no jobs section
- [x] 5.8 Implement kimi pilot side effect: for any kimi+pilot agent, generate `.agentweave/agent-<name>.yaml` and context markdown file
- [x] 5.9 Add `activate` subparser and routing in `create_parser()` / `main()`
- [x] 5.10 Add tests for each reconciliation step (transport, agents, MCP, watchdog, jobs)
- [x] 5.11 Add integration test: run `agentweave activate` twice, assert second run is a no-op

## 6. Documentation Updates

- [x] 6.1 Rewrite `docs/getting-started/quickstart.md` to use the 3-command flow: `hub start` → `init` → `activate`
- [x] 6.2 Add `agentweave.yml` reference page under `docs/reference/` documenting all fields, types, and examples
- [x] 6.3 Update `docs/getting-started/installation.md` to remove manual Hub bootstrap steps
- [x] 6.4 Update `README.md` Quick Start section to reflect new flow
- [x] 6.5 Add migration guide section: "Upgrading from manual setup" showing how existing users generate `agentweave.yml` from their current session
