## ADDED Requirements

### Requirement: An undelivered message SHALL say how its last attempt ended

The conversation SHALL show, where the Hub gave up delivering a message and a run was the last attempt to deliver it, how that run ended and the error it recorded, with the message and the Hub's reason for giving up.

The Hub keeps, on a message it gave up on, the run that last tried to deliver it. The conversation
is served that run's facts. A run that failed before its process started writes no output, so
without this the operator reads that delivery failed three times and not why, while the reason sits
on the run's own row.

The conversation SHALL learn that the Hub gave up on a message on every path that gives up, not only
the one that ends a run.

#### Scenario: A message whose runs failed to start says why

- **GIVEN** an agent whose runtime fails to start
- **WHEN** the operator's message is abandoned after its attempts fail
- **THEN** the message shows that it was not delivered, with the Hub's reason
- **AND** it shows that the last attempt failed, with the error that attempt
  recorded

#### Scenario: A message the Hub gave up on without a run shows only the Hub's reason

- **WHEN** the Hub gives up on a message without starting any run for it
- **THEN** the message shows that it was not delivered, with the Hub's reason
- **AND** it names no attempt

#### Scenario: Giving up without a run reaches an open conversation

- **GIVEN** the operator has the conversation open
- **WHEN** the Hub gives up on a message in it without starting a run
- **THEN** the message is shown as not delivered without a reload
