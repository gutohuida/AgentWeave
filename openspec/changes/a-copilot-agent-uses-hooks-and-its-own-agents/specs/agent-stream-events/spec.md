## ADDED Requirements

### Requirement: A Copilot run's compaction, errors and subagents reach its stream

The Hub SHALL record in a Copilot run's stream each compaction, each error and each subagent start, completion and failure that Copilot reports, as structured events carrying the facts Copilot reported.

These are the facts Copilot reports and the other runners do not: that the context was compacted and
by how much, what category an error belongs to and what would remedy it, and which subagent ran on
which model for how long. They SHALL come from Copilot's structured session events on the connection
the Hub already reads, and SHALL NOT depend on a hook process.

An error Copilot reports SHALL be recorded as an error event, not as a diagnostic, so that it stays
visible when diagnostics are hidden.

An error SHALL be recorded as one fact. Copilot reports an error as a structured event and then as
message text derived from it. The stream SHALL hold one error event for it and SHALL NOT also hold
that message text, and any other text around it SHALL be recorded as it would be without the error.
Where the structured event does not arrive, the message text SHALL be recorded as it is without
this change.

A compaction that Copilot reports as failed SHALL be recorded as a diagnostic, not as a compaction,
because the context was not replaced. A compaction Copilot reports for one of its subagents SHALL NOT
be recorded as a compaction of the run's conversation, because that conversation's context was not
replaced. A compaction whose report was too large for Copilot to relay SHALL still be recorded as a
compaction, with whatever counts Copilot reported when it began.

The counts Copilot reports (tokens before and after, the window, a subagent's tokens) SHALL be
stored as the numbers reported. Redaction SHALL apply to the text an event carries, and SHALL NOT
replace a count because of the name of its field.

Recording an error SHALL NOT itself place or lift a hold on the agent's queue.

#### Scenario: A compaction is recorded with its size

- **WHEN** Copilot reports a successful compaction of a run's conversation
- **THEN** the run's stream holds a status event naming the compaction
- **AND** it carries the context tokens before and after and the window it targeted, as numbers,
  and what triggered it, as Copilot reported it

#### Scenario: A compaction too large to relay still counts

- **WHEN** Copilot reports a compaction whose report was too large to relay in full
- **THEN** the run's stream holds a status event naming the compaction
- **AND** it carries the counts Copilot reported when the compaction began, where it reported them

#### Scenario: A subagent's compaction is not the conversation's

- **WHEN** Copilot reports that one of its subagents compacted its own context
- **THEN** no compaction status event is recorded for the run's conversation

#### Scenario: A failed compaction is not a compaction

- **WHEN** Copilot reports a compaction that did not succeed
- **THEN** the stream holds a diagnostic naming the failed compaction
- **AND** no compaction status event is recorded

#### Scenario: An error is recorded once

- **WHEN** Copilot reports an error as a structured event and then as message text in the same turn
- **THEN** the stream holds exactly one error event for it, carrying its category, status code and
  remediation where reported
- **AND** the stream holds no text event repeating it

#### Scenario: Text around an error is kept

- **WHEN** the agent had written message text in the same message before Copilot reported an error
- **THEN** the stream holds that text as text
- **AND** holds the error once, as an error event

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
