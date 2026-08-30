## ADDED Requirements

### Requirement: A question whose wait ended without an answer is listed as such

Where a checkpoint lists a conversation's open questions, a question whose bounded wait ended without an answer SHALL still be listed, and SHALL be listed as one whose wait ended rather than as one still awaiting a reply.

Both halves matter and they pull in opposite directions. Dropping it would lose the most useful
entry on that list: the successor is being handed work where a decision was taken without the
operator, and the question is what names the decision. Listing it unqualified tells the successor
that an answer is still coming, so the successor waits for it, or defers to it, or re-asks — when
what actually happened is that its predecessor already chose and moved on.

This is the one place the distinction reaches another agent rather than the operator, which is why
it is stated here rather than left to the surfaces that report a wait to a person.

#### Scenario: An ended wait is listed and marked

- **GIVEN** a conversation whose run asked a blocking question and whose wait ended without an answer
- **WHEN** a checkpoint is generated for that conversation
- **THEN** the question is present in the checkpoint's open questions
- **AND** it states that its wait ended without an answer

#### Scenario: A question still being waited on is listed unmarked

- **WHEN** a checkpoint is generated while a run is still waiting on a question it asked
- **THEN** that question is listed with no statement that its wait ended
