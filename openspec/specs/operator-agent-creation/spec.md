# operator-agent-creation Specification

## Purpose
Define how an operator creates a project-scoped, runner-bound agent from the Hub while preserving
launchability truth, optional charter guidance, stable identity, and lazy worktree isolation.
## Requirements
### Requirement: An operator can create an agent from the project workspace

Each project workspace SHALL expose an **Add agent** action. Creating an agent SHALL require a
valid project-unique name, a launchable provider, and a model that provider's catalog entry
declares. A charter MAY be selected but MUST NOT be required. The operator MUST NOT be asked to
choose a persona or organizational role.

The operator MUST NOT be required to have configured a runner beforehand. Selecting a provider and
a model SHALL be sufficient to create a working agent.

#### Scenario: A minimally configured agent is created

- **WHEN** the operator supplies a valid unused name and selects a launchable provider and a model
- **THEN** the agent is created with a stable project color and runner binding
- **AND** it appears in the project rail without a reload
- **AND** its conversation opens ready for input

#### Scenario: No runner need exist beforehand

- **WHEN** the operator selects a provider and model for which the project has no runner
- **THEN** creation succeeds and the agent is bound to a runner for that provider and model

#### Scenario: The offered models come from the catalog

- **WHEN** the operator selects a provider
- **THEN** the models offered are those the catalog declares for that provider

#### Scenario: A charter is optional

- **WHEN** the operator creates an agent without selecting a charter
- **THEN** creation succeeds with full project scope under the existing no-charter contract

#### Scenario: A duplicate name is refused without losing input

- **WHEN** the supplied name already identifies an agent in that project
- **THEN** creation is refused with a field-specific reason
- **AND** the dialog preserves the operator's other selections for correction

### Requirement: Agent creation exposes real runner launchability

The creation journey SHALL display every provider it offers with that provider's current
launchability. An unlaunchable provider SHALL remain visible with the reason it cannot run and MUST
NOT be selectable as ready. The server SHALL repeat launchability validation when creation is
submitted.

#### Scenario: An unavailable provider is explained

- **WHEN** a provider's CLI or authorization is unavailable
- **THEN** the provider is displayed disabled with the current reason
- **AND** submitting that provider cannot create an apparently ready agent

#### Scenario: Client state cannot bypass server validation

- **WHEN** provider launchability changes after the dialog loads but before submission
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

### Requirement: Agent creation provisions its runner atomically

When agent creation requires a runner that does not exist, the Hub SHALL create the runner and the
agent as one atomic operation. A failure at any point SHALL leave neither record behind.

The Hub SHALL reuse an existing same-project runner whose provider and model match the operator's
selection rather than creating a duplicate.

#### Scenario: A matching runner is reused

- **WHEN** the operator creates a second agent on a provider and model that an existing runner in
  that project already describes
- **THEN** the new agent is bound to that existing runner
- **AND** no additional runner is created

#### Scenario: A failed creation leaves no runner behind

- **WHEN** agent creation fails after a runner would have been provisioned
- **THEN** no runner record remains from the attempt

#### Scenario: Provisioned runners are ordinary records

- **WHEN** a runner has been provisioned through agent creation
- **THEN** it appears in runner management and can be inspected, edited, and deleted like any other
