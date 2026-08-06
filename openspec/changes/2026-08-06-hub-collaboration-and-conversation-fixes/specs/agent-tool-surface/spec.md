## ADDED Requirements

### Requirement: An invocable tool surface is the default, not an opt-in

Where a provider offers more than one way to start a run, and only some of those ways permit the
Hub to answer approvals per request, the Hub SHALL select an invocable configuration by default.

An operator MUST NOT be required to set a flag, edit a runner record, or know a sentinel value in
order for a newly created agent's tool surface to be callable. A runner created through the Hub's
own agent-creation flow, with no further configuration, SHALL produce runs whose tool surface the
agent can actually call.

Where a less capable transport is retained for diagnostic or compatibility reasons, it SHALL be
reachable only by explicit opt-out, and the reported readiness of an agent SHALL reflect the
transport that will actually be used for its next run.

#### Scenario: A newly created agent can collaborate without configuration

- **WHEN** an operator creates an agent through the Hub's agent-creation flow and changes nothing else
- **AND** that agent's provider requires approvals before a tool call proceeds
- **THEN** its runs use a transport in which the Hub answers those approvals
- **AND** its tool calls to the Hub's own surface succeed

#### Scenario: The degraded transport requires an explicit opt-out

- **WHEN** a runner has not opted out of the invocable transport
- **THEN** the invocable transport is used

#### Scenario: Reported readiness matches the transport that will run

- **WHEN** an agent's collaboration readiness is reported
- **THEN** it reflects the transport its next run will actually use
- **AND** an agent that will use an invocable transport is not reported as unable to collaborate
