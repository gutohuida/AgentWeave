# operator-agent-creation Specification

## Purpose
Define how an operator creates a project-scoped, runner-bound agent from the Hub while preserving
launchability truth, optional charter guidance, stable identity, and lazy worktree isolation.
## Requirements
### Requirement: An operator can create an agent from the project workspace

Each project workspace SHALL expose an **Add agent** action. Creating an agent SHALL require a
valid project-unique name and a launchable same-project runner. A charter MAY be selected but MUST
NOT be required. The operator MUST NOT be asked to choose a persona or organizational role.

#### Scenario: A minimally configured agent is created

- **WHEN** the operator supplies a valid unused name and selects a launchable runner
- **THEN** the agent is created with a stable project color and runner binding
- **AND** it appears in the project rail without a reload
- **AND** its conversation opens ready for input

#### Scenario: A charter is optional

- **WHEN** the operator creates an agent without selecting a charter
- **THEN** creation succeeds with full project scope under the existing no-charter contract

#### Scenario: A duplicate name is refused without losing input

- **WHEN** the supplied name already identifies an agent in that project
- **THEN** creation is refused with a field-specific reason
- **AND** the dialog preserves the operator's other selections for correction

### Requirement: Agent creation exposes real runner launchability

The creation journey SHALL display every same-project runner with its current launchability. An
unlaunchable runner SHALL remain visible with the reason it cannot run and MUST NOT be selectable as
ready. The server SHALL repeat launchability validation when creation is submitted.

#### Scenario: An unavailable runner is explained

- **WHEN** a configured runner's CLI or authorization is unavailable
- **THEN** the runner is displayed disabled with the current reason
- **AND** submitting that runner cannot create an apparently ready agent

#### Scenario: Client state cannot bypass server validation

- **WHEN** runner launchability changes after the dialog loads but before submission
- **THEN** the server refuses creation with the current typed reason

### Requirement: Operator-created agents preserve runtime isolation

An operator-created agent SHALL be a Hub-owned project participant with its own queue, conversation
identity, and stable color. Creation SHALL NOT provision or mutate a Git worktree. The existing
scheduler SHALL provision the isolated worktree only when the agent first begins writing work.

#### Scenario: Creation has no filesystem side effect beyond Hub state

- **WHEN** an operator creates an agent but sends it no work
- **THEN** no agent worktree exists

#### Scenario: First writing turn provisions isolation

- **WHEN** the new agent begins its first writing turn
- **THEN** the scheduler provisions that agent's isolated worktree under the existing project guard
- **AND** other agents' worktrees and the primary checkout remain unchanged
