## ADDED Requirements

### Requirement: Agent signals liveness via heartbeat
The system SHALL provide a `heartbeat(agent)` MCP tool that self-registered agents call periodically to signal they are still active. The Hub SHALL record each heartbeat with a timestamp.

#### Scenario: Heartbeat accepted
- **WHEN** a self-registered agent calls `heartbeat(agent="hermes")`
- **THEN** the Hub writes a record to `AgentHeartbeat` with the current timestamp
- **AND** returns `{ ok: true }`

#### Scenario: Heartbeat from unknown agent
- **WHEN** `heartbeat()` is called for an agent name with no registration record
- **THEN** the Hub returns `{ ok: false, error: "Agent 'hermes' is not registered" }`

### Requirement: Hub dashboard shows self-registered agents
The Hub UI SHALL display self-registered agents in the agents panel alongside session-configured agents. Each self-registered agent SHALL be visually distinguished with a badge.

#### Scenario: Self-registered agent appears in dashboard
- **WHEN** an agent successfully calls `register_agent()`
- **THEN** the agent appears in the Hub agents panel
- **AND** displays a "self-registered" or "external" badge to distinguish it from configured agents

#### Scenario: GET /api/v1/agents includes self-registered agents
- **WHEN** the Hub API receives `GET /api/v1/agents`
- **THEN** the response includes both session-configured agents and self-registered agents
- **AND** each entry includes a `self_registered` boolean field

### Requirement: Liveness status derived from last heartbeat
The Hub SHALL expose each self-registered agent's liveness status based on the age of its most recent heartbeat. An agent is considered online if a heartbeat was received within the last 2 minutes.

#### Scenario: Agent is online
- **WHEN** the most recent heartbeat for an agent was less than 2 minutes ago
- **THEN** the agent's status is `online` in the API response and dashboard

#### Scenario: Agent is offline
- **WHEN** no heartbeat has been received for an agent in more than 2 minutes
- **OR** the agent has never sent a heartbeat after registering
- **THEN** the agent's status is `offline` in the API response and dashboard
