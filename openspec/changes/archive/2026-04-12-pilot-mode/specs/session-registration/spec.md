## ADDED Requirements

### Requirement: MCP tool to register session
The CLI MCP server SHALL expose a `register_session(session_id: str)` tool that pilots can call from their interactive session to register their active `--resume` session ID with the Hub.

#### Scenario: Successful registration via MCP
- **WHEN** a pilot agent calls `register_session("sess-abc123")`
- **THEN** the Hub SHALL store `registered_session_id = "sess-abc123"` for that agent
- **AND** `.agentweave/agent-context/{agent}.md` SHALL be regenerated with current roles
- **AND** the tool SHALL return the ready-to-use launch command string

#### Scenario: Re-registration replaces previous session
- **WHEN** a pilot agent calls `register_session` with a new session ID
- **THEN** the Hub SHALL overwrite the previously stored session ID
- **AND** only the latest session ID is retained

#### Scenario: MCP tool called without Hub transport
- **WHEN** `register_session` is called and no HTTP transport is configured
- **THEN** the tool SHALL update `.agentweave/agents/{agent}-session.json` locally
- **AND** print the launch command using the local agent-context file

### Requirement: Hub API endpoint for session registration
The Hub SHALL expose `POST /api/v1/agents/{agent}/register-session` accepting `{ "session_id": "<id>" }`.

#### Scenario: Valid registration request
- **WHEN** a POST request is made with a valid session ID
- **THEN** the Hub SHALL update `registered_session_id` on the agent record
- **AND** return `{ "success": true, "agent": "<name>", "session_id": "<id>" }`

#### Scenario: Agent does not exist
- **WHEN** a registration request names an unknown agent
- **THEN** the Hub SHALL create the agent record with `pilot: true` and the session ID
- **AND** return success

### Requirement: CLI command to register session
`agentweave session register --agent <agent> --session <session_id>` SHALL register the session ID for the named agent.

#### Scenario: Register session via CLI
- **WHEN** user runs `agentweave session register --agent claude --session sess-abc123`
- **THEN** the session ID SHALL be stored in Hub (if HTTP transport) or locally
- **AND** `.agentweave/agent-context/claude.md` SHALL be regenerated
- **AND** the CLI SHALL print the launch command

#### Scenario: Launch command output format (Claude)
- **WHEN** session is registered for a claude or claude_proxy agent
- **THEN** the printed launch command SHALL be:
  `claude --resume <session_id> --append-system-prompt-file .agentweave/agent-context/<agent>.md`

#### Scenario: Launch command output format (Kimi)
- **WHEN** session is registered for a kimi agent
- **THEN** the printed launch command SHALL be:
  `kimi --session <session_id>`
- **AND** a note SHALL be printed that role context is injected via prompt on first message

### Requirement: Hub UI session registration form
The Hub UI SHALL provide a form on the agent card or info tab for manually entering and submitting a session ID for a pilot agent.

#### Scenario: Register session via Hub UI
- **WHEN** user enters a session ID in the register form and submits
- **THEN** the Hub SHALL call `POST /api/v1/agents/{agent}/register-session`
- **AND** the agent card SHALL update to show the new session ID

#### Scenario: Registered session displayed on agent card
- **WHEN** an agent has a `registered_session_id`
- **THEN** the agent info tab SHALL display it labeled "Active Session"
- **AND** the session ID SHALL be copyable
