## MODIFIED Requirements

### Requirement: One tool surface, configured automatically

The Hub SHALL expose a single tool surface for agents. A second, separately maintained surface with
equivalent tools MUST NOT exist.

Because the Hub starts the agent, it SHALL supply the agent's tool configuration when starting it.
An operator MUST NOT be required to edit an agent client's configuration file to make the tool
surface available.

A tool surface the Hub has configured SHALL be invocable by the agent it was configured for. The
Hub MUST NOT start a run whose tool surface it has configured but which it knows the agent cannot
call. Where a provider requires approval before a tool call proceeds, the Hub SHALL supply that
approval as part of starting the run.

Making the tool surface invocable MUST NOT require weakening any other protection the operator
selected for that run. In particular, the agent's filesystem sandboxing SHALL be unchanged by
whatever makes the tool surface callable.

#### Scenario: Tools are available without operator configuration

- **WHEN** an agent is started by the Hub for the first time
- **THEN** its tool surface is available
- **AND** the operator edited no agent client configuration file

#### Scenario: Only one surface exists

- **WHEN** the available tools are inspected
- **THEN** exactly one surface provides them

#### Scenario: A configured tool can actually be called

- **WHEN** an agent started by the Hub calls a tool from its configured surface
- **THEN** the call proceeds to the Hub
- **AND** is not refused for want of an approval the operator was never asked for

#### Scenario: Collaboration does not cost the sandbox

- **WHEN** an agent whose run is filesystem-sandboxed calls a tool from its configured surface
- **THEN** the call proceeds
- **AND** the run remains filesystem-sandboxed

#### Scenario: An uninvocable surface is refused, not pretended

- **WHEN** the Hub determines that a run's tool surface cannot be made invocable
- **THEN** the Hub records a diagnostic naming the reason
- **AND** does not present the run as having a working tool surface

### Requirement: An agent's identity is bound by the Hub, never asserted by the agent

An agent's identity SHALL be established by the Hub when it starts the agent, and every effect the
agent causes SHALL be attributed to that identity and run. The application API and every adapter
MUST NOT accept an identity supplied by the caller, and MUST NOT fall back to an unattributed or
placeholder identity.

An agent MUST NOT be able to cause an effect attributed to another agent. Binding an environment
variable without validating a live run credential SHALL NOT by itself satisfy this requirement.

A run credential SHALL be honoured only by the Hub instance that issued it. A Hub instance
receiving an agent action bearing a credential it did not issue SHALL refuse the action and SHALL
NOT apply its effect, whatever database that instance holds.

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

#### Scenario: A credential from another instance is refused

- **WHEN** a Hub instance receives an agent action bearing a run credential it did not issue
- **THEN** the action is refused as unattributable
- **AND** no effect is written to that instance's records

## ADDED Requirements

### Requirement: An agent is told the address of the Hub that started it

The Hub SHALL supply each run with the address of the Hub instance that started it, and that
address SHALL be the address the instance is actually serving on.

The address MUST NOT be derived from a configured default, an assumed port, or any value that can
differ from the address in use. Where the operator has explicitly supplied an external address for
the Hub, that address SHALL take precedence, because it is a deliberate deployment statement rather
than an assumption.

If the Hub can determine neither an operator-supplied address nor the address it is serving on, it
SHALL refuse to start the run and record the reason. It MUST NOT start a run carrying a guessed
address.

#### Scenario: The supplied address matches the serving address

- **WHEN** a Hub serving on a given address starts a run
- **THEN** the run is given that address
- **AND** the address does not depend on any configured default

#### Scenario: A non-default port is handled correctly

- **WHEN** a Hub is started on a port other than its configured default and then starts a run
- **THEN** the run is given the port the Hub is actually serving on

#### Scenario: An explicit external address wins

- **WHEN** the operator has explicitly supplied an external address for the Hub
- **THEN** runs are given that address in preference to the observed one

#### Scenario: An undeterminable address stops the run

- **WHEN** the Hub can determine neither an explicit nor an observed address
- **THEN** it refuses to start the run
- **AND** records the reason

### Requirement: A failed tool call is reported, not silently absorbed

When a tool call made by an agent fails, the failure SHALL be reported to the agent with enough
detail to distinguish its cause, and SHALL be recorded by the Hub where the Hub is able to observe
it.

The report SHALL identify which endpoint the call was directed at, so that a call delivered
somewhere other than the intended Hub is diagnosable from the agent's own record of the turn.

A failure the Hub observes SHALL be recorded as an event on the causing agent's timeline, alongside
the run's other recorded outcomes.

#### Scenario: A failure names its destination

- **WHEN** an agent's tool call fails
- **THEN** the reported failure identifies the endpoint the call was directed at

#### Scenario: A failure distinguishes its cause

- **WHEN** an agent's tool call fails
- **THEN** the report distinguishes a rejected request from an unreachable or unintended destination

#### Scenario: An observed failure reaches the operator

- **WHEN** the Hub observes a tool call fail
- **THEN** an event recording the failure and its reason appears on the causing agent's timeline
