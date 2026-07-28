## ADDED Requirements

### Requirement: Pilot flag on agent config
Each agent in `session.json` MAY have a `pilot` boolean field (default: `false`). When `pilot: true`, the agent is considered human-controlled for all execution decisions.

#### Scenario: Pilot flag persists to Hub
- **WHEN** `session.json` is saved with `pilot: true` for an agent
- **THEN** the Hub DB record for that agent SHALL have `pilot = true`

#### Scenario: Pilot flag defaults to false
- **WHEN** an agent config has no `pilot` key
- **THEN** the system SHALL treat it as `pilot: false` with no behavior change

### Requirement: Watchdog skips auto-execution for pilot agents
The watchdog MUST NOT invoke the agent CLI for any agent with `pilot: true`.

#### Scenario: New message for pilot agent
- **WHEN** a new message addressed to a pilot agent is detected in the Hub
- **THEN** the watchdog SHALL skip CLI execution for that message
- **AND** the message SHALL remain unread in the Hub inbox
- **AND** the watchdog SHALL log a debug note that execution was skipped (pilot mode)

#### Scenario: New message for non-pilot agent
- **WHEN** a new message addressed to a non-pilot agent is detected
- **THEN** the watchdog SHALL execute the agent CLI as normal

#### Scenario: Watchdog stale-message warning still fires for pilot
- **WHEN** a message to a pilot agent remains unread beyond the retry_after threshold
- **THEN** the watchdog SHALL print the stale-message warning as usual
- **AND** SHALL NOT auto-execute the agent CLI

### Requirement: Hub trigger endpoint respects pilot flag
The `POST /api/v1/agent/trigger` endpoint MUST NOT queue a trigger message for execution when the target agent has `pilot: true`.

#### Scenario: Trigger requested for pilot agent
- **WHEN** a trigger request is sent for a pilot agent
- **THEN** the endpoint SHALL create the message in the DB (so it appears in inbox)
- **AND** SHALL return a response indicating pilot mode is active
- **AND** SHALL NOT attempt CLI execution

#### Scenario: Trigger requested for non-pilot agent
- **WHEN** a trigger request is sent for a non-pilot agent
- **THEN** behavior is unchanged from current implementation

### Requirement: CLI command to set pilot flag
`agentweave agent configure <agent> --pilot` SHALL enable pilot mode for the named agent. `--no-pilot` SHALL disable it.

#### Scenario: Enable pilot mode via CLI
- **WHEN** user runs `agentweave agent configure claude --pilot`
- **THEN** `session.json` SHALL be updated with `pilot: true` for `claude`
- **AND** the change SHALL be pushed to Hub if HTTP transport is active

#### Scenario: Disable pilot mode via CLI
- **WHEN** user runs `agentweave agent configure claude --no-pilot`
- **THEN** `session.json` SHALL be updated with `pilot: false` for `claude`

### Requirement: Hub UI pilot badge
Agent cards in the Hub UI SHALL display a `PILOT` badge for agents with `pilot: true`.

#### Scenario: Pilot agent card
- **WHEN** viewing the agents page and an agent has `pilot: true`
- **THEN** the agent card SHALL display a `PILOT` badge alongside the runner badge

#### Scenario: Trigger button disabled for pilot agents
- **WHEN** viewing a pilot agent's card or prompt panel
- **THEN** the trigger/send button SHALL be disabled
- **AND** SHALL show a tooltip: "Pilot mode — agent is manually controlled"
