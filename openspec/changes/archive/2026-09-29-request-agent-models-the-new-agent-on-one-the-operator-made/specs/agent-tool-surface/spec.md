## ADDED Requirements

### Requirement: An agent request is modelled on an agent the operator made

A request by an agent for a further agent SHALL name, as its template, an open agent of the same project, and the new agent SHALL be created with that agent's bound runner, charter and runner configuration.

The operator approves a kind of agent by creating one. A template source that no surface writes
approves nothing, and a tool whose only input has no producer refuses every call while being
described to agents as available.

The new agent SHALL NOT inherit authority the operator grants one agent at a time — the grants to
accept evidence, to read other agents' checkpoints and to recall observations — nor its default
permission posture, in any spelling the spawn reads, nor that agent's description or per-agent
overrides. A new agent runs under the built-in default posture until the operator sets one. An agent MUST NOT be able to create a second holder of a grant
the operator gave to one.

A declaration that changes which tools a run is given, and through that its posture, SHALL NOT be
inherited either: the operator's statement that an agent runs without the Hub's own tool server is
made about that agent alone. A per-agent override carried in the template's runner environment,
such as how long it waits for an answer, SHALL NOT be inherited any more than the same override
written on the agent.

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

#### Scenario: A full-access template does not produce a full-access agent

- **GIVEN** a template agent the operator set to run with full access
- **WHEN** an agent is requested from it
- **THEN** the new agent's first turn is not started with full access
- **AND** its settings show the built-in default posture

#### Scenario: A template declared to run without the Hub's tool server does not pass that on

- **GIVEN** a template agent the operator declared to run without the Hub's own tool server
- **WHEN** an agent is requested from it
- **THEN** the new agent carries no such declaration
- **AND** its first turn is not started under the posture a run without that server falls back to

#### Scenario: A waiting override in the runner environment is not inherited

- **GIVEN** a template agent whose runner environment sets how long it waits for an answer
- **WHEN** an agent is requested from it
- **THEN** the new agent keeps the template's other runner environment settings
- **AND** it waits for an answer for the Hub's default time

#### Scenario: An unknown template names what would work

- **WHEN** a request names a template that is not an agent of the project
- **THEN** the request is refused
- **AND** the refusal lists the project's open agents

#### Scenario: The budget still bounds it

- **GIVEN** the project already has as many agents as its agent budget
- **WHEN** an agent is requested from a valid template
- **THEN** the request is refused and no agent is created
