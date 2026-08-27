## ADDED Requirements

### Requirement: A turn admits entries of one kind only

The system SHALL, where an agent's queue holds both a review entry and a work entry in the same
conversation, deliver a turn carrying only the controlling entry's kind — the same entry that
decides the turn's depth (see "The hop budget bounds delivery, not only admission"). An entry of the
other kind SHALL remain queued and SHALL be delivered on a later turn — held back, not refused and
not dropped, the same treatment an over-budget entry already gets.

#### Scenario: A turn admits only the controlling entry's kind

- **GIVEN** an agent's queue holds a review entry and a work entry in the same conversation
- **WHEN** the review entry is the earliest admitted
- **THEN** the delivered turn carries only the review entry
- **AND** the work entry remains queued

#### Scenario: The reverse arrival order gives the reverse outcome

- **GIVEN** an agent's queue holds a review entry and a work entry in the same conversation
- **WHEN** the work entry is the earliest admitted
- **THEN** the delivered turn carries only the work entry
- **AND** the review entry remains queued

#### Scenario: A deferred entry is not starved

- **GIVEN** an entry left queued because a turn admitted only the other kind
- **WHEN** the agent's next turn is scheduled
- **THEN** the deferred entry is delivered

### Requirement: A delivered turn carries a review or ordinary work, never both

The system SHALL refuse to start a turn whose queued input asks the agent both to review a task and
to work on a task. The refusal SHALL name both tasks and SHALL state that a turn has one subject.

A turn has one workspace. A turn asked to do both is given the review checkout, because that is what
preparing a review means — and is then bound to whichever task an ordering rule happens to select,
which need not be the one it is looking at. A run bound to work the agent was never shown is worse
than an unbound run: an unbound run is exempt from the check that asks whether it moved its task,
while this one fails that check against work it was never given.

This is defence in depth. The requirement above already keeps the normal scheduling path from ever
assembling a mixed batch; this refusal is what catches a caller that hands `queue_entry_ids` to the
trigger directly, bypassing that narrowing.

Refusing SHALL happen before the agent is started, so that no workspace is prepared and no turn is
delivered.

#### Scenario: A turn batching a review and a work item is refused

- **GIVEN** queued input containing an entry naming a task to review and an entry naming a different
  task to work on
- **WHEN** a turn is started from that input
- **THEN** the turn is refused
- **AND** the reason names both tasks and states that a turn has one subject
- **AND** no agent process is started

#### Scenario: A review batched with a work item naming the same task is still refused

- **GIVEN** queued input containing an entry naming a task to review and an entry naming that same
  task to work on
- **WHEN** a turn is started from that input
- **THEN** the turn is refused

#### Scenario: Several work items in one turn are still allowed

- **GIVEN** queued input containing more than one entry naming a task to work on and no review
- **WHEN** a turn is started from that input
- **THEN** the turn is delivered
- **AND** the run is bound to one of those tasks by the existing ordering rule

#### Scenario: A review alone is unaffected

- **GIVEN** queued input containing one or more entries naming the same task to review and no work
- **WHEN** a turn is started from that input
- **THEN** the turn is delivered with the review checkout
- **AND** the run is bound to the task under review

#### Scenario: Refusal leaves the input where it was

- **GIVEN** a turn refused for batching a review and ordinary work
- **WHEN** the operator inspects the agent's queue
- **THEN** the entries are still queued
- **AND** none is marked delivered
