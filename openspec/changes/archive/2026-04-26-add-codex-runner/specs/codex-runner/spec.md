## ADDED Requirements

### Requirement: Codex runner type declared in constants
The system SHALL define a `codex` entry in `RUNNER_TYPES`, `RUNNER_CONFIGS`, and `AGENT_RUNNER_DEFAULTS` in `constants.py`.

`RUNNER_CONFIGS["codex"]` SHALL contain:
- `cli`: `"codex"`
- `subcommand`: `"exec"`
- `session_flag`: `"resume"`
- `output_format`: `"json"`
- `session_source`: `"jsonl"`
- `session_id_field`: `"thread_id"`
- `session_event_type`: `"thread.started"`
- `model_flag`: `"--model"`
- `context_flag`: `["-c", "model_instructions_file={path}"]`
- `mcp_add_cmd`: `["codex", "mcp", "add", "{name}", "--", "{server_cmd}"]`

`AGENT_RUNNER_DEFAULTS["codex"]` SHALL be `"codex"`.

#### Scenario: Runner config lookup
- **WHEN** code calls `RUNNER_CONFIGS["codex"]`
- **THEN** the dict contains all keys listed above with correct values

---

### Requirement: Watchdog builds correct headless command
The watchdog SHALL build `codex exec --json [-c model_instructions_file=<path>] [--model <model>] [-c memory_mode=disabled] "<prompt>"` for the first ping of a Codex agent.

#### Scenario: First ping, no session
- **WHEN** the watchdog pings a Codex agent with no stored thread_id
- **THEN** the command is `codex exec --json "<prompt>"` (plus optional flags)

#### Scenario: Context file present
- **WHEN** `.agentweave/agents/<agent>.md` exists
- **THEN** `-c model_instructions_file=<path>` is appended to the command

#### Scenario: Model configured
- **WHEN** `session.get_runner_config(agent)["model"]` is set
- **THEN** `--model <model>` is appended to the command

---

### Requirement: Watchdog resumes via thread_id
The watchdog SHALL build `codex exec resume <thread_id> --json "<prompt>"` when a stored thread_id exists for the agent.

#### Scenario: Resume with stored thread_id
- **WHEN** `.agentweave/agents/<agent>-session.json` contains a `thread_id`
- **THEN** the command becomes `codex exec resume <thread_id> --json "<prompt>"`

#### Scenario: Session file missing
- **WHEN** no session file exists for the agent
- **THEN** the command omits the resume subcommand and starts fresh

---

### Requirement: Watchdog parses thread_id from JSONL stream
The watchdog SHALL extract the thread_id from the first `thread.started` event in the `codex exec --json` stdout stream and save it to `.agentweave/agents/<agent>-session.json`.

#### Scenario: Successful thread_id extraction
- **WHEN** `codex exec --json` outputs `{"type":"thread.started","thread_id":"<uuid>"}`
- **THEN** the watchdog saves `{"thread_id": "<uuid>"}` to the agent session file

#### Scenario: Process completes before thread.started emitted
- **WHEN** no `thread.started` event appears in stdout
- **THEN** the watchdog logs a warning and leaves the existing session file unchanged

---

### Requirement: Watchdog suppresses expected Codex stderr noise
The watchdog SHALL suppress the line `failed to record rollout items` from Codex stderr before logging or surfacing output.

#### Scenario: Known noise suppressed
- **WHEN** Codex stderr contains `"failed to record rollout items"`
- **THEN** the line is not forwarded to the Hub log stream or printed to the terminal

#### Scenario: Unknown stderr forwarded
- **WHEN** Codex stderr contains any other content
- **THEN** it is forwarded normally

---

### Requirement: MCP setup registers AgentWeave server with Codex
`agentweave mcp-setup` SHALL register the AgentWeave MCP server with a Codex agent using `codex mcp add <name> -- <server_cmd>`.

#### Scenario: MCP setup for Codex agent
- **WHEN** `agentweave mcp-setup` runs and an agent has `runner: codex`
- **THEN** it executes `codex mcp add agentweave -- <server_cmd>`

---

### Requirement: `agentweave agent configure` supports Codex
`agentweave agent configure <name> --runner codex` SHALL initialise the agent with the codex runner and prompt for `CODEX_API_KEY` if not set in the environment.

#### Scenario: Configure codex runner
- **WHEN** user runs `agentweave agent configure my-codex --runner codex`
- **THEN** the agent is created with `runner: codex` in session config

#### Scenario: Missing API key warning
- **WHEN** `CODEX_API_KEY` is not set in the environment
- **THEN** a warning is printed: `"CODEX_API_KEY not set — Codex will fail at runtime"`
