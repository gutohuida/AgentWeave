## 1. constants.py — Runner Registration

- [x] 1.1 Add `"opencode"` to `RUNNER_TYPES` list
- [x] 1.2 Add `RUNNER_CONFIGS["opencode"]` entry with `cli`, `subcommand`, `session_flag`, `output_format`, `context_flag`, `model_flag`, `mcp_add_cmd=None`
- [x] 1.3 Add `"opencode": "opencode"` to `AGENT_RUNNER_DEFAULTS`
- [x] 1.4 Add `"opencode"` to `KNOWN_AGENTS` with descriptive comment

## 2. watchdog.py — Dispatch Logic

- [x] 2.1 Add `opencode` branch in `_agent_ping_cmd()` that builds `["opencode", "run", ...]`
- [x] 2.2 Include `--model` flag when agent config has a model set
- [x] 2.3 Use stable session ID `agentweave-{agent}` and include `--session` flag on every invocation after first ping
- [x] 2.4 Inject `--file .agentweave/context/{agent}.md` when the context file exists
- [x] 2.5 Append `--format json` and the prompt as the final positional argument
- [x] 2.6 Ensure exit-code monitoring works for opencode (reuses existing subprocess handling — verify no stream-json parsing is assumed)

## 3. cli.py — MCP Setup File Writer

- [x] 3.1 Add `_write_opencode_mcp_config(server_cmd)` helper that reads, merges, and writes `opencode.json`
- [x] 3.2 Handle missing `opencode.json` (create from scratch)
- [x] 3.3 Handle existing `opencode.json` with other keys (merge, preserve all other keys)
- [x] 3.4 Handle malformed `opencode.json` (print error + manual snippet, exit non-zero, do not overwrite)
- [x] 3.5 In `cmd_mcp_setup()`, detect `mcp_add_cmd is None` for opencode agents and call the file-based writer instead of subprocess
- [x] 3.6 Print the path of the written `opencode.json` in mcp-setup output (e.g. `[OK] opencode-dev: opencode.json updated`)
- [x] 3.7 Add opencode launch instructions to `cmd_switch()` output (follow the kimi/claude pattern)

## 4. config.py — Validation

- [x] 4.1 Confirm `_validate_agent_config()` accepts `runner: opencode` (it reads from `RUNNER_TYPES` which is updated in 1.1 — verify no hardcoding)
- [x] 4.2 Confirm `generate_agentweave_yml()` serializes opencode agents correctly (runner + model fields round-trip)

## 5. Tests

- [x] 5.1 `tests/test_watchdog.py`: test `_agent_ping_cmd` builds correct command for opencode runner with no session, with session, with model, with context file
- [x] 5.2 `tests/test_cli.py`: test `_write_opencode_mcp_config` creates new file, merges into existing file, handles malformed JSON gracefully
- [x] 5.3 `tests/test_config.py`: test `load_agentweave_yml` accepts `runner: opencode` with local model, cloud model, and no model; test round-trip via `generate_agentweave_yml`
- [x] 5.4 `tests/test_constants.py`: assert `"opencode"` is in `RUNNER_TYPES`, `RUNNER_CONFIGS`, `AGENT_RUNNER_DEFAULTS`, `KNOWN_AGENTS`

## 6. Documentation

- [x] 6.1 Add `docs/guides/opencode-agents.md` — setup guide covering install, agentweave.yml config, mcp-setup, and Ollama local model setup
- [x] 6.2 Update `docs/getting-started/configuration.md` — add opencode to the runner type reference table
- [x] 6.3 Update `CLAUDE.md` — add `"opencode"` to the RUNNER_TYPES list in the architecture overview
