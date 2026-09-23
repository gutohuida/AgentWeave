## ADDED Requirements

### Requirement: An agent request is modelled on an agent the operator made

A request by an agent for a further agent SHALL name, as its template, an open agent of the same project, and the new agent SHALL be created with that agent's bound runner, charter and runner configuration.

The operator approves a kind of agent by creating one. A template source that no surface writes
approves nothing, and a tool whose only input has no producer refuses every call while being
described to agents as available.

The new agent SHALL NOT inherit authority the operator grants one agent at a time — the grants to
accept evidence, to read other agents' checkpoints and to recall observations — nor that agent's
description or per-agent overrides. An agent MUST NOT be able to create a second holder of a grant
the operator gave to one.

A request naming no such agent SHALL be refused with the names of the project's open agents it could
have named. A request naming an archived agent, or an agent with no runner bound, SHALL be refused
saying so. The agent budget SHALL be counted over the project's agents alone.

#### Scenario: A request modelled on an operator's agent creates a runnable agent

- **GIVEN** the operator created an agent with a bound runner and a charter
- **WHEN** another agent's run requests a new agent naming it as the template, within the agent budget
- **THEN** the new agent exists with the same runner and charter
- **AND** its first turn is queued and is not held for want of a runner

#### Scenario: Grants are not inherited

- **GIVEN** a template agent the operator granted authority to accept evidence
- **WHEN** an agent is requested from it
- **THEN** the new agent holds no such grant

#### Scenario: An unknown template names what would work

- **WHEN** a request names a template that is not an agent of the project
- **THEN** the request is refused
- **AND** the refusal lists the project's open agents

#### Scenario: The budget still bounds it

- **GIVEN** the project already has as many agents as its agent budget
- **WHEN** an agent is requested from a valid template
- **THEN** the request is refused and no agent is created
