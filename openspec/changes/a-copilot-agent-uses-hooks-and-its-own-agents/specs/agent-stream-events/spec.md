## ADDED Requirements

### Requirement: A Copilot run's compaction, errors and subagents reach its stream

The Hub SHALL record in a Copilot run's stream each compaction, each error and each subagent start, completion and failure that Copilot reports, as structured events carrying the facts Copilot reported.

These are the facts Copilot reports and the other runners do not: that the context was compacted and
by how much, what category an error belongs to and what would remedy it, and which subagent ran on
which model for how long. They SHALL come from Copilot's structured session events on the connection
the Hub already reads, and SHALL NOT depend on a hook process.

An error Copilot reports SHALL be recorded as an error event, not as a diagnostic, so that it stays
visible when diagnostics are hidden.

An error SHALL be recorded as one fact. Where Copilot reports an error both as a structured event and
as message text, the stream SHALL hold one error event for it and SHALL NOT also hold the message
text, whichever of the two arrives first. Where the structured event does not arrive, the message
text SHALL be recorded as it is without this change.

A compaction that Copilot reports as failed SHALL be recorded as a diagnostic, not as a compaction,
because the context was not replaced.

The counts Copilot reports (tokens before and after, the window, a subagent's tokens) SHALL be
stored as the numbers reported. Redaction SHALL apply to the text an event carries, and SHALL NOT
replace a count because of the name of its field.

Recording an error SHALL NOT itself place or lift a hold on the agent's queue.

#### Scenario: A compaction is recorded with its size

- **WHEN** Copilot reports a successful compaction of a run's conversation
- **THEN** the run's stream holds a status event naming the compaction
- **AND** it carries the context tokens before and after, the window it targeted, and whether it was
  automatic or requested, as numbers

#### Scenario: A failed compaction is not a compaction

- **WHEN** Copilot reports a compaction that did not succeed
- **THEN** the stream holds a diagnostic naming the failed compaction
- **AND** no compaction status event is recorded

#### Scenario: An error is recorded once, in either order

- **WHEN** Copilot reports an error as a structured event and as message text in the same turn
- **THEN** the stream holds exactly one error event for it, carrying its category, status code and
  remediation where reported
- **AND** the stream holds no text event repeating it
- **AND** this holds whether the structured event or the message text arrives first

#### Scenario: An error stays visible when diagnostics are hidden

- **WHEN** Copilot reports an error and the operator has hidden diagnostics
- **THEN** the error is still shown

#### Scenario: Without the structured event the text still counts

- **WHEN** an error reaches the Hub only as message text
- **THEN** it is recorded as it is without this change

#### Scenario: A subagent's run is paired with the call that started it

- **WHEN** a Copilot run starts a subagent and the subagent completes or fails
- **THEN** the stream holds a start event and an end event carrying the parent call's identifier
- **AND** the end event carries the subagent's model, tokens and duration where reported, and the
  failure's message when it failed

#### Scenario: Recording a quota error adds no hold of its own

- **WHEN** an error event whose category is quota or rate limit is recorded
- **THEN** the recording neither places nor lifts a hold on the agent's queue
- **AND** any hold is placed only where holds are already decided from the run's allowance reading
