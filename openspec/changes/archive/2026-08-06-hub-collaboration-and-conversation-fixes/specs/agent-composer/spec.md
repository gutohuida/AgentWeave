## REMOVED Requirements

### Requirement: In-place agent selector

**Reason:** The composer's target-agent selector let a message typed in one agent's conversation be
delivered to a different agent. Because the send path is not scoped to the visible conversation, a
retargeted message left no trace in the conversation the operator was looking at unless the app
happened to navigate away. The operator reported the affordance as counterintuitive and asked for
its removal.

**Migration:** None required. `POST /api/v1/agent/trigger` is unchanged and remains the Hub's single
trigger entry point, used by handoffs and deliver-now. To address a different agent, open that
agent's conversation. Launchability and collaboration readiness, previously visible only inside this
selector, are surfaced on the agent's card instead.

## ADDED Requirements

### Requirement: The composer addresses the conversation it belongs to

A message submitted from a conversation SHALL be delivered to that conversation's agent. The
composer MUST NOT offer a control that redirects a submission to a different agent.

#### Scenario: A submission targets the current agent

- **WHEN** the operator submits a message from agent `A`'s conversation
- **THEN** the submission targets `A`

#### Scenario: No redirect control is offered

- **WHEN** the composer's control row is displayed
- **THEN** it contains no control for selecting a different recipient agent
