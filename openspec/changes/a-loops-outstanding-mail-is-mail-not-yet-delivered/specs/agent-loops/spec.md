## MODIFIED Requirements

### Requirement: An empty queue with a request still in flight terminates, and is recorded

When a loop's stop condition fires because its queue is empty, the Hub SHALL check whether an
unanswered request for more work — a message to the loop's creator, or an unanswered question — was
outstanding at that moment, and SHALL record what it found as part of stopping the loop. The loop
SHALL still stop; an outstanding request SHALL NOT create a third, waiting state.

A message is outstanding only while it is waiting to be delivered into one of its recipient's turns.
A message that has been delivered is no longer outstanding, and neither is one whose delivery the
Hub withdrew or abandoned, since it will never arrive. Whether a message is outstanding SHALL be
decided from its delivery, not from a flag no part of the Hub sets.

#### Scenario: The queue empties with no outstanding request

- **WHEN** a loop's queue empties and no message to its creator or unanswered question is
  outstanding
- **THEN** the loop stops
- **AND** the stop is recorded with no pending request noted

#### Scenario: The queue empties while a request for more work is outstanding

- **WHEN** a loop's queue empties while its executor has a message to the creator still waiting to
  be delivered, or an unanswered question outstanding
- **THEN** the loop still stops
- **AND** the stop is recorded noting the outstanding request, so it can be reviewed later

#### Scenario: A message the creator has received is not outstanding

- **GIVEN** a message from the loop's executor to its creator that has been delivered into one of
  the creator's turns
- **WHEN** the loop's queue empties
- **THEN** the stop is recorded with no pending request noted on account of that message

#### Scenario: A message that will never arrive is not outstanding

- **GIVEN** a message from the loop's executor to its creator whose delivery the Hub withdrew or
  abandoned
- **WHEN** the loop's queue empties
- **THEN** the stop is recorded with no pending request noted on account of that message
