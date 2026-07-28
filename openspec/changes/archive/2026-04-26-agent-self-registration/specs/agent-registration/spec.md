## ADDED Requirements

### Requirement: Agent can self-register via MCP
Any MCP-capable agent with a valid project API key SHALL be able to register itself into an active AgentWeave Hub session by calling `register_agent()`. Registration requires only the agent's name and contact mode. Registration is idempotent — calling it multiple times with the same name updates metadata and returns the current role and context without error.

#### Scenario: Successful first-time registration
- **WHEN** an agent calls `register_agent(name="hermes", contact_mode="poll")`
- **THEN** the Hub creates a registration record with `self_registered=true`
- **AND** returns `{ role: "<assigned_role>", context: "<role_guide_content>" }`

#### Scenario: Re-registration after compaction
- **WHEN** an already-registered agent calls `register_agent()` again with the same name
- **THEN** the Hub updates `last_seen` on the existing record
- **AND** returns the same role and context without error

#### Scenario: Registration with optional role hint
- **WHEN** an agent calls `register_agent(name="hermes", contact_mode="poll", role_request="worker")`
- **THEN** the Hub assigns a role, using the hint as guidance
- **AND** the final assigned role is returned in the response

#### Scenario: Name collision with configured agent
- **WHEN** an agent calls `register_agent()` with a name that already exists in the session's configured agent list (e.g., "claude" or "kimi")
- **THEN** the Hub returns an error: `{ error: "Agent name '<name>' is reserved for a configured agent" }`

#### Scenario: Registration on non-HTTP transport
- **WHEN** `register_agent()` is called against a local or git transport MCP server
- **THEN** the system returns an error: `{ error: "Self-registration requires Hub (HTTP) transport" }`

### Requirement: Contact mode is declared at registration
The `contact_mode` field SHALL be required at registration and stored in the Hub DB. It governs how AgentWeave reaches the agent when there is pending work.

#### Scenario: Poll mode stored correctly
- **WHEN** an agent registers with `contact_mode="poll"`
- **THEN** the Hub stores `contact_mode="poll"` on the Agent record
- **AND** the watchdog skips this agent when checking whether to spawn or notify

#### Scenario: Invalid contact mode rejected
- **WHEN** an agent registers with an unrecognized `contact_mode` value
- **THEN** the Hub returns an error listing valid modes

### Requirement: Watchdog skips self-registered poll agents
The watchdog SHALL NOT attempt to spawn or ping agents that are self-registered with `contact_mode="poll"`. These agents manage their own inbox polling.

#### Scenario: Watchdog ignores poll agent
- **WHEN** the watchdog processes pending work for an agent
- **AND** that agent is self-registered with `contact_mode="poll"`
- **THEN** the watchdog skips the agent without spawning any process

#### Scenario: Watchdog still processes configured agents
- **WHEN** the watchdog processes pending work for Claude or Kimi
- **THEN** behavior is identical to before this change — no skip, normal spawn
