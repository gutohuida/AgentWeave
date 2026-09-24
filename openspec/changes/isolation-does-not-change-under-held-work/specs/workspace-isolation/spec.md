## ADDED Requirements

### Requirement: Whether an agent works in its own checkout does not change while it holds work

The Hub SHALL refuse a change to whether an agent works in its own checkout while that agent has a turn in progress or is assigned a task that has not been approved or rejected.

Changing it moves where the agent's next turn runs. Work already in the old location — a task
checkout, or uncommitted edits in the project's own checkout — stays where the agent no longer
looks, and a task-bound turn in the project's checkout is not committed onto the task's branch.

Whether an agent works in its own checkout SHALL be judged on the configuration the Hub actually
reads when it chooses the agent's workspace — the agent's stored configuration with the project's
synced session state for that agent applied over it — before and after the request. A request whose
effect that configuration overrides is not a change.

The refusal SHALL apply on every operation that changes that configuration, including one that
replaces the project's synced session state, and SHALL name each turn and task that holds it and
what would clear it. A refused request SHALL change nothing — neither the agent nor, for a session
replacement, the session state or the roster.

A request that leaves the setting as it was SHALL NOT be refused on these grounds.

#### Scenario: Isolation cannot be switched off under an open task

- **WHEN** the operator sets an agent to share the project checkout while it is assigned an in-progress task
- **THEN** the request is refused, naming the task
- **AND** the agent's configuration is unchanged

#### Scenario: Isolation cannot be switched on under a live turn

- **WHEN** the operator sets a sharing agent to work in its own checkout while it has a turn in progress
- **THEN** the request is refused, naming the turn

#### Scenario: Re-registering is held to the same rule

- **WHEN** an agent re-registers with a configuration that changes whether it works in its own checkout while it holds an open task
- **THEN** the registration is refused and nothing about the agent changes

#### Scenario: Replacing the synced session state is held to the same rule

- **WHEN** the synced session state is replaced with an entry that changes whether an agent holding an open task works in its own checkout
- **THEN** the replacement is refused, naming the agent and the task
- **AND** the session state and the roster are unchanged

#### Scenario: A change the session state overrides is not a change

- **WHEN** the synced session state fixes whether an agent works in its own checkout and a request changes only the agent's stored value for it, while the agent holds an open task
- **THEN** the request is accepted, because where the agent works does not change

#### Scenario: An idle agent can be changed

- **WHEN** the agent has no turn in progress and no open task
- **THEN** the change is accepted

#### Scenario: Other settings are not held

- **WHEN** a request changes other configuration and leaves isolation as it was
- **THEN** it is accepted whatever the agent is doing
