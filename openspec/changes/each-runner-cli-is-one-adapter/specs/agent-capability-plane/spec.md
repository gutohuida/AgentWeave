## ADDED Requirements

### Requirement: A run's tool surface, approval channel and plane access are decided separately

For every run, the Hub SHALL resolve three separate values, and SHALL take the run's approval channel from the transport the run uses rather than from whether the Hub's tool server is provided, except where that channel is carried by the tool server. The three values are: whether the Hub's tool server is provided to the run (its tool surface), which channel, if any, lets the Hub answer the run's tool calls (its approval channel), and how the run is given access to the capability plane (its plane access). The plane access is over the tool protocol exactly when the tool server is provided.

A single value used to answer all three. For some runners the three move together. For others they do not:
- A peer that asks the Hub over its own protocol can have its calls approved whether or not the Hub's tool server
  was provided to it.
- A harness whose only approver is a tool on the Hub's tool server cannot.

A run's approval channel SHALL be withdrawn by a change to its tool surface **only** where that channel is carried by
the tool surface. The operator's statement that a run has no tool-protocol surface SHALL remove the tool server. It
SHALL NOT remove an approval channel that does not depend on the tool server.

A run's permission posture at rest SHALL be decided from its approval channel. A posture that names the Hub as the
answerer SHALL be the default only where the run has an approval channel. What the run is told about its access
remains decided separately, from grounds, as before. Resolving these three values SHALL NOT widen any run's
containment.

#### Scenario: A harness whose approver is a Hub tool loses it with the tool server

- **WHEN** the operator states that a Claude run has no tool-protocol surface
- **THEN** that run is given no tool server and no approval channel
- **AND** its default posture is the one that needs no answerer

#### Scenario: A peer that asks over its own protocol keeps its approvals

- **WHEN** the operator states that a Codex run on its app-server transport has no tool-protocol surface
- **THEN** that run is given no tool server
- **AND** the Hub still answers that run's approval requests under the posture the operator chose

#### Scenario: A transport with no live approvals has no approval channel

- **WHEN** a Codex run uses its exec transport
- **THEN** its approval channel is none, whatever its tool surface is

#### Scenario: The default case is unchanged

- **WHEN** a Claude run, or a Codex run on its app-server transport, starts with no statement from the operator about
  its access
- **THEN** it is given the tool server, an approval channel, and plane access over the tool protocol, exactly as before
  the values were separated
