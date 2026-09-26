## ADDED Requirements

### Requirement: A message the hop budget holds is reported to its sender as not delivered

Where an agent sends a message that is queued past the project's hop budget, the answer to that send SHALL state that the message was recorded and will not be delivered unless the operator continues the chain or raises the budget, and SHALL NOT be only the answer an ordinary send receives.

A message queued past the budget is delivered only if the operator acts. The sender reads the
answer to its send and nothing else about the message: no later briefing tells it what became of
it. Answered exactly as an ordinary send, it tells a colleague the message arrived, and a chain of
work that was waiting on that message stops with nobody saying so.

The answer SHALL name the depth and the budget, and SHALL name what would deliver the message. It
SHALL NOT tell the sender to send the message again, because a resend from the same turn is queued
at the same depth and held the same way.

The answer SHALL still report the send as recorded, with the message's identifier. The message
exists, the operator can see it, and it can still be delivered; reporting a failure would invite a
retry that is held in turn.

A message queued within the budget SHALL be answered as it is today.

#### Scenario: A held message tells its sender

- **WHEN** an agent's turn at the project's hop budget sends a message to another agent
- **THEN** the answer reports the message as recorded, with its identifier
- **AND** it states that the message will not be delivered unless the operator continues the chain or raises the budget
- **AND** it names the depth and the budget

#### Scenario: A held message does not invite a resend

- **WHEN** a sent message is held by the hop budget
- **THEN** the answer does not tell the sender to send it again

#### Scenario: A message within the budget is answered as before

- **WHEN** an agent's turn below the project's hop budget sends a message
- **THEN** the answer is what an ordinary send receives, with no statement about holding
