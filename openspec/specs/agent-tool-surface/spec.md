# agent-tool-surface

## Purpose

Defines what an agent may do through HTTP, MCP, and ordinary commands, and how that access is
established. Originated by `openspec/changes/2026-07-30-hub-native-experience`; the identity
requirement below carries the `openspec/changes/agent-capability-plane` revision (run-credential
authentication in place of environment-variable binding). `openspec/changes/single-runtime` removed
the per-runner access-path selection and command-based-fallback requirements below, since it deletes
the CLI collaboration commands they depended on — HTTP and MCP are the only two paths now.

## Requirements

### Requirement: The Hub supplies state; the tool surface carries intent

The system SHALL supply everything an agent needs in order to begin a turn — its queued entries,
the roster of its collaborators, its charter, and its project's instructions — at the start of
that turn.

The tool surface exposed to an agent SHALL therefore be limited to **causing effects** in shared
state. A tool MUST NOT allow an agent to read coordination state that was not supplied to it, and
MUST NOT allow an agent to alter its own configuration or scope.

#### Scenario: An agent begins a turn already holding what it needs

- **WHEN** a turn begins
- **THEN** the agent has its queued entries, roster, charter, and project instructions
- **AND** it need invoke no tool to obtain them

#### Scenario: Coordination state cannot be read around the Hub

- **WHEN** an agent attempts to read queued or undelivered entries directly
- **THEN** no tool provides them

#### Scenario: An agent cannot widen its own scope

- **WHEN** an agent attempts to alter its own charter, scope, or configuration
- **THEN** no tool permits it

### Requirement: Outbound intent remains available

An agent SHALL retain the ability to message another agent, to create and update work in the shared
task ledger, to read the task ledger, and to ask the operator a question and receive an answer.

These SHALL remain available because they are the agent's only means of affecting shared state, and
each is attributable to the agent and turn that performed it.

#### Scenario: An agent can affect shared state

- **WHEN** an agent sends a message, creates or updates a task, or asks the operator a question
- **THEN** the effect is applied
- **AND** it is attributed to that agent and turn

#### Scenario: Messages sent through the tool surface obey the queue

- **WHEN** an agent sends a message to another agent
- **THEN** it enters the recipient's queue as an entry with a hop depth
- **AND** it is subject to the hop budget

### Requirement: Creating agents and scheduling recurring work are governed, not free

A tool that causes a new agent to exist SHALL be subject to the project's agent budget. A tool that
creates, enables, or triggers recurring scheduled work SHALL be governed by the operator, either by
budget or by explicit approval.

No tool SHALL allow an agent to bring another agent into existence outside the agent budget.

#### Scenario: Agent creation cannot escape the budget

- **WHEN** an agent uses the tool surface to request a further agent
- **THEN** the request is subject to the project's agent budget and approval rules

#### Scenario: Scheduling recurring work requires governance

- **WHEN** an agent creates, enables, or triggers recurring scheduled work
- **THEN** the action is either within a configured allowance or awaits operator approval

### Requirement: An agent's identity is bound by the Hub, never asserted by the agent

An agent's identity SHALL be established by the Hub when it starts the agent, and every effect the
agent causes SHALL be attributed to that identity and run. The application API and every adapter
MUST NOT accept an identity supplied by the caller, and MUST NOT fall back to an unattributed or
placeholder identity.

An agent MUST NOT be able to cause an effect attributed to another agent. Binding an environment
variable without validating a live run credential SHALL NOT by itself satisfy this requirement.

#### Scenario: Identity comes from authenticated run capability

- **WHEN** an agent causes any effect through HTTP, MCP, or command access
- **THEN** it is attributed to the live run credential established by the Hub
- **AND** no caller-supplied identity is accepted

#### Scenario: Impersonation is impossible

- **WHEN** an agent attempts to cause an effect as another agent
- **THEN** the attempt is refused or remains attributed to its authenticated run

#### Scenario: There is no unattributed effect

- **WHEN** any effect is recorded
- **THEN** it names the agent and run that caused it
- **AND** no effect is recorded against an unknown or placeholder identity

### Requirement: One tool surface, configured automatically

The Hub SHALL expose a single tool surface for agents. A second, separately maintained surface with
equivalent tools MUST NOT exist.

Because the Hub starts the agent, it SHALL supply the agent's tool configuration when starting it.
An operator MUST NOT be required to edit an agent client's configuration file to make the tool
surface available.

#### Scenario: Tools are available without operator configuration

- **WHEN** an agent is started by the Hub for the first time
- **THEN** its tool surface is available
- **AND** the operator edited no agent client configuration file

#### Scenario: Only one surface exists

- **WHEN** the available tools are inspected
- **THEN** exactly one surface provides them
