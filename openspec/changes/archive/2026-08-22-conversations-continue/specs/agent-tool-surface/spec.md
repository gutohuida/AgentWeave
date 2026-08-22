## ADDED Requirements

### Requirement: The outbound message tool describes how delivery is actually resolved

The published description of the outbound message tool SHALL describe the delivery rule the Hub
enforces. It MUST NOT describe a rule the Hub no longer applies.

The tool schema is the agent's only documentation of the surface; an agent cannot read the Hub's
source to discover that the description is stale. A description that names a superseded rule is
worse than none, because it is acted on.

The description of the parameter that names a recipient conversation SHALL state what omitting it
does — resolve by binding — rather than stating that it selects the recipient's most recent
conversation. Recency selection was removed when the binding contract shipped, and the description
has named it since.

The description SHALL state that a new thread is started only by explicit request or by checkpoint
cutover, so that an agent has no reason to expect one to appear on its own.

#### Scenario: The description matches the enforced rule

- **WHEN** the outbound message tool's published description of delivery is compared with the rule
  the Hub applies
- **THEN** they agree

#### Scenario: Omitting the recipient conversation is described as binding, not recency

- **WHEN** an agent inspects the parameter that names a recipient conversation
- **THEN** the description states that omitting it resolves delivery by binding
- **AND** it does not state that the recipient's most recent conversation is used

#### Scenario: Starting a new thread is described as deliberate

- **WHEN** an agent inspects the outbound message tool
- **THEN** the parameter that starts a new thread is declared with its default
- **AND** the description states that continuing is what happens when it is omitted
