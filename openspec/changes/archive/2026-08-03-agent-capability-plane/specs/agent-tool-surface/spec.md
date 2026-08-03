## MODIFIED Requirements

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

- **WHEN** any agent-plane effect is recorded
- **THEN** it names the agent and run that caused it
- **AND** no effect is recorded against an unknown or placeholder identity
