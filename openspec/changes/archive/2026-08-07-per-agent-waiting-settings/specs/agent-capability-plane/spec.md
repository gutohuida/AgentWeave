## ADDED Requirements

### Requirement: How long an agent waits for the operator is a per-agent setting

Each agent SHALL carry its own limit for how long it waits on a permission decision and on an answer
to a question, and an agent with no limit set SHALL use the system default.

How long a wait is reasonable depends on the agent and on whether the operator is watching. A single
compiled-in number serves neither the agent being supervised closely nor the one left running while
the operator is elsewhere.

#### Scenario: A configured wait governs the run

- **WHEN** an agent with its own waiting limits starts a run
- **THEN** that run waits for the operator for the configured time rather than the default

#### Scenario: An unconfigured agent is unchanged

- **WHEN** an agent with no waiting limits set starts a run
- **THEN** it waits for the system default, exactly as it did before the setting existed

#### Scenario: A limit outside the permitted range is refused

- **WHEN** a waiting limit is set below the minimum or above the maximum
- **THEN** the change is refused and the stored value is unchanged

#### Scenario: An unreadable setting does not break the run

- **WHEN** a run's waiting limit cannot be read or understood
- **THEN** the run uses the default rather than failing

#### Scenario: A run in flight keeps the rules it started under

- **WHEN** an agent's waiting limit is changed while one of its runs is already in progress
- **THEN** that run continues under the limit it started with

### Requirement: Durable per-agent settings are edited on the agent, not in the composer

Settings that belong to an agent rather than to one conversation SHALL be presented on the agent's
own surface, reachable from a conversation without leaving it.

The composer's controls are per-conversation and chosen at the moment of sending. Mixing durable
per-agent configuration into them would make it unclear which choices persist, and adding a third
settings location would make it unclear where to look.

#### Scenario: The operator changes a durable setting mid-conversation

- **WHEN** the operator opens the agent's settings from a conversation
- **THEN** the setting is presented there
- **AND** the conversation is not discarded or reset

#### Scenario: Per-conversation controls stay per-conversation

- **WHEN** the operator views the composer's controls
- **THEN** they offer only choices scoped to that conversation, not durable agent settings
