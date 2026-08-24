## ADDED Requirements

### Requirement: The hop budget bounds delivery, not only admission

An inbound queue entry whose hop depth exceeds the project's hop budget SHALL NOT be delivered to an
agent's turn, regardless of what other entries are delivered in the same turn.

A turn's depth SHALL be the depth of the entry that admitted the turn. It SHALL NOT be derived from
the lowest depth among the entries delivered, and a turn SHALL NOT be recorded at a depth lower than
that of any entry it delivers.

#### Scenario: An over-budget entry is not carried by an in-budget one

- **GIVEN** a project whose hop budget is exceeded by one queued agent-originated entry
- **AND** a second entry in the same conversation that is within budget
- **WHEN** the agent's turn starts
- **THEN** only the within-budget entry is delivered
- **AND** the over-budget entry remains queued

#### Scenario: An operator message does not release a blocked chain

- **GIVEN** an agent-originated entry held back because its hop depth exceeds the budget
- **WHEN** the operator sends a message into the same conversation
- **THEN** the operator's message is delivered
- **AND** the over-budget entry remains queued
- **AND** the resulting turn's depth is the operator message's depth

#### Scenario: The depth counter does not run backwards

- **GIVEN** a turn admitted by an entry at a given hop depth
- **WHEN** the agent sends a message during that turn
- **THEN** the resulting entry's hop depth is greater than the admitting entry's depth

### Requirement: An entry held back by the hop budget is visible and has a stated exit

The Hub SHALL report an entry that is queued because its hop depth exceeds the budget as held for
that reason, distinguishably from an entry queued for any other reason.

The operator SHALL be able to release such an entry deliberately. Releasing it SHALL re-base its
depth so that it and the chain it continues start again from the operator's own depth, and SHALL be
recorded as an operator decision.

The operator SHALL also be able to discard such an entry. An entry held by the budget SHALL NOT be
left with no way forward and no way out.

#### Scenario: The operator releases a held chain

- **GIVEN** an entry held back because its hop depth exceeds the budget
- **WHEN** the operator chooses to continue that chain
- **THEN** the entry is delivered on the agent's next turn
- **AND** the decision to release it is recorded
- **AND** messages the agent sends during that turn are within budget again

#### Scenario: The operator discards a held chain

- **GIVEN** an entry held back because its hop depth exceeds the budget
- **WHEN** the operator discards it
- **THEN** it is withdrawn and never delivered

#### Scenario: Raising the budget releases what it was holding

- **GIVEN** one or more entries held back because their hop depth exceeds the budget
- **WHEN** the operator raises the project's hop budget above those depths
- **THEN** those entries become deliverable without any further operator action
