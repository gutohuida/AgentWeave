## ADDED Requirements

### Requirement: A live run credential is the only agent authentication

The system SHALL mint an unguessable credential for each Hub-owned run, store only a non-reversible
digest, and accept the credential only while that exact run is active. Authentication SHALL derive
the project, agent, and run from the matched row. The credential MUST NOT be exposed in output,
events, command arguments, or API responses.

#### Scenario: Active run resolves to one actor

- **WHEN** an agent request carries a valid credential for a running run
- **THEN** the server derives that run's project and agent
- **AND** the request supplies no actor identity

#### Scenario: Terminal run is revoked

- **WHEN** a credential belongs to a completed, failed, stopped, or interrupted run
- **THEN** the agent request is refused

#### Scenario: Credentials cannot cross privilege planes

- **WHEN** a project API key is presented to the agent API or a run credential is presented to an
  operator API
- **THEN** authentication is refused

### Requirement: The agent API is a least-privilege allowlist

The agent application API SHALL expose only peer messaging, shared task-ledger reads/writes,
operator questions and their answers, governed agent requests, and governed scheduled-work
mutations. It MUST NOT expose inbound queue/history, roster, project settings, agent configuration,
charter/scope, credentials, or other operator capabilities.

#### Scenario: Outbound intent is available

- **WHEN** an authenticated run messages a peer, works with the shared task ledger, or asks the
  operator a question
- **THEN** the permitted effect or read succeeds under the same validation as the operator system

#### Scenario: Coordination and configuration are absent

- **WHEN** an authenticated run tries to read undelivered input or alter project/agent configuration
- **THEN** no agent API operation provides that capability

#### Scenario: New operator APIs are denied by default

- **WHEN** an operator-only route is added without an explicit agent capability
- **THEN** a run credential cannot call it

### Requirement: Actor identity cannot be supplied or overridden

Agent-action payloads SHALL contain no project, agent, sender, assigner, requester, or run identity
field. Every affected service SHALL use only the authenticated actor. Caller headers or extra body
fields MUST NOT change attribution.

#### Scenario: Impersonation is structurally unavailable

- **WHEN** an agent constructs a valid action request
- **THEN** there is no supported field by which it can select another actor

#### Scenario: Override attempts do not change the actor

- **WHEN** a caller adds identity-like headers or unknown body fields
- **THEN** the effect is either rejected as invalid or remains attributed to the authenticated run

### Requirement: Every agent-caused effect retains run attribution

The system SHALL ensure every message, task creation/update, question, scheduled-work mutation, and
agent request caused by the agent plane durably identifies the responsible agent and run. Event logs MUST NOT be the
only source of that attribution. Historical/operator effects MAY remain unattributed where no run
exists.

#### Scenario: Persisted effect names its run

- **WHEN** an authenticated run causes an allowed effect
- **THEN** the resulting durable record identifies that run
- **AND** its project and agent are consistent with the authenticated actor

#### Scenario: Updates retain the latest responsible run

- **WHEN** an authenticated run updates a mutable task or job
- **THEN** the record identifies the run responsible for that update

### Requirement: HTTP, MCP, and command access have equal capability

Direct HTTP SHALL be the application contract. MCP and ordinary commands SHALL be thin adapters
over that contract with the same operations, validation, governance, attribution, and typed failure
meaning. Adapters MUST NOT duplicate queue, budget, identity, or lifecycle business rules and MUST
NOT silently convert failures into empty or successful results.

#### Scenario: One operation has one persisted result

- **WHEN** equivalent valid actions are performed through HTTP, MCP, and command access
- **THEN** their persisted effects have equivalent content and attribution

#### Scenario: Failure meaning survives adaptation

- **WHEN** the application API returns validation, denied, not-found, or conflict failure
- **THEN** MCP and command callers receive the same failure meaning

#### Scenario: No full project credential is present

- **WHEN** the Hub starts an agent with either adapter available
- **THEN** the process receives its run credential
- **AND** it does not receive a project/operator API key
