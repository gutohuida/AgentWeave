## ADDED Requirements

### Requirement: The Hub supplies state; the tool surface carries intent

Everything an agent needs in order to begin a turn — its queued entries, the roster of its
collaborators, its charter, and its project's instructions — SHALL be supplied by the Hub at the
start of that turn.

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
agent causes SHALL be attributed to that identity. The tool surface MUST NOT accept an identity
supplied by the caller, and MUST NOT fall back to an unattributed or placeholder identity.

An agent MUST NOT be able to cause an effect attributed to another agent.

#### Scenario: Identity comes from the run, not the request

- **WHEN** an agent causes any effect through the tool surface
- **THEN** it is attributed to the identity the Hub established for that run
- **AND** no caller-supplied identity is accepted

#### Scenario: Impersonation is impossible

- **WHEN** an agent attempts to cause an effect as another agent
- **THEN** the attempt is refused

#### Scenario: There is no unattributed effect

- **WHEN** any effect is recorded
- **THEN** it names the agent and run that caused it
- **AND** no effect is recorded against an unknown or placeholder identity

### Requirement: The access path is chosen per runner from probed capability

Whether an agent reaches the tool surface through a tool-protocol server or through commands SHALL
be determined by the capability of its runner in the current environment, established by the Hub
rather than configured by hand for each agent.

Runners differ in this respect within a single environment, and a runner that supports a
tool-protocol server in general may be prohibited from using one locally. The Hub SHALL record what
is actually available, not what is theoretically supported.

An operator MAY override the chosen path for a runner.

#### Scenario: Runners in one environment resolve differently

- **WHEN** one runner permits a tool-protocol server and another does not, on the same machine
- **THEN** each agent uses the path available to its runner
- **AND** neither required per-agent configuration

#### Scenario: Prohibited is distinguished from unsupported

- **WHEN** a runner supports a tool-protocol server but is prohibited from connecting to one
- **THEN** the Hub records it as unavailable in this environment and uses commands

#### Scenario: The operator can override

- **WHEN** an operator selects a path for a runner
- **THEN** that choice is used in place of the probed capability

### Requirement: The tool surface is available without a tool-protocol server

Every outbound capability SHALL be reachable by an agent through an ordinary command invocation, in
addition to any tool-protocol server the Hub provides. An environment that permits no tool-protocol
server SHALL remain fully supported.

Selecting the command-based path MUST NOT reduce what an agent can do, and MUST NOT bypass the
queue, the hop budget, the agent budget, or attribution.

The Hub SHALL tell the agent which path is in use, so the agent does not attempt an unavailable one.

#### Scenario: A restricted environment loses no capability

- **WHEN** an agent runs where no tool-protocol server is permitted
- **THEN** it can still message another agent, create and update tasks, read the task ledger, ask
  the operator a question, and request an agent
- **AND** every effect is attributed as it would be otherwise

#### Scenario: Governance holds on the command-based path

- **WHEN** an agent uses a command to message another agent or request a further agent
- **THEN** the hop budget, agent budget, and queue apply unchanged

#### Scenario: The agent is told which path to use

- **WHEN** a turn begins
- **THEN** the agent is told whether to use the tool-protocol server or commands
- **AND** it is not offered a path unavailable in that environment

#### Scenario: Turn-start state needs no tools at all

- **WHEN** an agent runs where no tool-protocol server is permitted
- **THEN** its queued entries, roster, charter, and project instructions are still supplied at turn
  start without any tool invocation

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
