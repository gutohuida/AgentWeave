## ADDED Requirements

### Requirement: OpenCode runner type is registered in constants
The system SHALL define `"opencode"` in `RUNNER_TYPES` and provide a complete `RUNNER_CONFIGS["opencode"]` entry with keys: `cli`, `subcommand`, `session_flag`, `output_format`, `context_flag`, `model_flag`, and `mcp_add_cmd` set to `None`.

#### Scenario: RUNNER_TYPES includes opencode
- **WHEN** a developer inspects `RUNNER_TYPES` in `constants.py`
- **THEN** `"opencode"` SHALL be present in the list alongside `"claude"`, `"kimi"`, `"claude_proxy"`, `"native"`, `"manual"`

#### Scenario: RUNNER_CONFIGS opencode entry is complete
- **WHEN** `RUNNER_CONFIGS["opencode"]` is accessed
- **THEN** it SHALL contain `cli="opencode"`, `subcommand="run"`, `session_flag="--session"`, `output_format="json"`, `context_flag="--file"`, `model_flag="--model"`, and `mcp_add_cmd=None`

---

### Requirement: Watchdog dispatches tasks to OpenCode agents
The system SHALL build a valid `opencode run` command when `_agent_ping_cmd()` is called for an agent with `runner: opencode`.

#### Scenario: Basic dispatch without session or model
- **WHEN** `_agent_ping_cmd("opencode-dev", "do the task")` is called and no session ID or model is configured
- **THEN** the returned command SHALL be `["opencode", "run", "--format", "json", "do the task"]`

#### Scenario: Dispatch with stable session ID
- **WHEN** the agent has been pinged before and a session ID `agentweave-opencode-dev` exists
- **THEN** the command SHALL include `["--session", "agentweave-opencode-dev"]` before the prompt

#### Scenario: Dispatch with model flag
- **WHEN** the agent config has `model: ollama/qwen2.5-coder:7b`
- **THEN** the command SHALL include `["--model", "ollama/qwen2.5-coder:7b"]`

#### Scenario: Role file injected when present
- **WHEN** `.agentweave/context/opencode-dev.md` exists
- **THEN** the command SHALL include `["--file", ".agentweave/context/opencode-dev.md"]` before the prompt

#### Scenario: Role file omitted when absent
- **WHEN** `.agentweave/context/opencode-dev.md` does not exist
- **THEN** the command SHALL NOT include any `--file` flag

---

### Requirement: Stable session IDs are used for OpenCode agents
The system SHALL use `agentweave-{agent}` as the session ID for OpenCode agents to ensure session continuity across watchdog pings without parsing streamed output.

#### Scenario: Session ID is deterministic per agent name
- **WHEN** an OpenCode agent named `opencode-dev` is pinged for the first time
- **THEN** the session ID written to `.agentweave/agents/opencode-dev-session.json` SHALL be `agentweave-opencode-dev`

#### Scenario: Same session ID is reused on subsequent pings
- **WHEN** an OpenCode agent named `opencode-dev` is pinged again after a prior run
- **THEN** the `--session agentweave-opencode-dev` flag SHALL be included in the command

---

### Requirement: MCP server is registered in opencode.json for OpenCode agents
When `agentweave mcp-setup` is run and the session contains an OpenCode agent, the system SHALL write or update `opencode.json` in the project root to include AgentWeave's MCP server entry.

#### Scenario: opencode.json does not exist
- **WHEN** `agentweave mcp-setup` is run and `opencode.json` does not exist
- **THEN** `opencode.json` SHALL be created with `{"mcp": {"agentweave": {"type": "local", "command": ["agentweave-mcp"]}}}`

#### Scenario: opencode.json exists with other config
- **WHEN** `agentweave mcp-setup` is run and `opencode.json` exists with other keys
- **THEN** only the `mcp.agentweave` key SHALL be written or overwritten; all other keys SHALL be preserved

#### Scenario: opencode.json is malformed
- **WHEN** `agentweave mcp-setup` is run and `opencode.json` contains invalid JSON
- **THEN** the system SHALL print an error, display the manual config snippet, and exit with a non-zero status without overwriting the file

#### Scenario: mcp-setup reports written path
- **WHEN** `agentweave mcp-setup` succeeds for an opencode agent
- **THEN** the output SHALL include the path to the written `opencode.json` file

---

### Requirement: opencode is listed in KNOWN_AGENTS
The system SHALL include `"opencode"` in the `KNOWN_AGENTS` list in `constants.py` with a descriptive comment.

#### Scenario: KNOWN_AGENTS contains opencode entry
- **WHEN** a developer inspects `KNOWN_AGENTS`
- **THEN** `"opencode"` SHALL appear with a comment such as `# OpenCode (sst.dev) — model-neutral terminal coding agent`
