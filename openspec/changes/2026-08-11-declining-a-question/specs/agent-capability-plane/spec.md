# Agent capability plane — deltas

## ADDED Requirements

### Requirement: The operator may decline a question

The system SHALL let the operator close an outstanding question without answering it, and SHALL
record that they did.

Declining SHALL be available to the operator only. An agent SHALL NOT decline a question, including
one it asked itself: an agent able to close its own question could clear the record of having asked
without anyone having decided anything.

A question that has already been answered SHALL NOT be declinable.

#### Scenario: An outstanding question can be closed unanswered

- **WHEN** the operator declines an outstanding question
- **THEN** the question is no longer outstanding
- **AND** it carries no answer

#### Scenario: An answered question cannot be declined

- **WHEN** a question that has been answered is declined
- **THEN** the request is refused
- **AND** the recorded answer is unchanged

#### Scenario: The agent surface offers no way to decline

- **WHEN** an agent enumerates the operations available to it
- **THEN** none of them declines a question

### Requirement: A waiting agent is told that its question was declined

Where an agent is waiting on a question, the system SHALL end that wait when the question is
declined, rather than leaving it to expire, and SHALL report the decline distinctly from both an
answer and an expiry.

A decline and an expiry mean different things. An expiry means nobody was there; a decline means
someone was there and chose not to answer, which tells the agent the decision is now its own. An
agent left to time out spends the interval waiting for something already decided and then arrives at
a weaker conclusion than the one available.

The report SHALL NOT present a decline as an answer. What an agent does with a decline is its own
judgement, and the system SHALL NOT require any particular response to one.

#### Scenario: A decline ends the wait

- **WHEN** an agent is waiting on a question and the operator declines it
- **THEN** the wait ends without waiting for the expiry
- **AND** the agent is told the question was declined

#### Scenario: A decline is not reported as an answer

- **WHEN** an agent receives the outcome of a declined question
- **THEN** the outcome states that no answer was given
- **AND** it is distinguishable from a question that expired unanswered

#### Scenario: A mixed batch reports each outcome

- **WHEN** an agent asked several questions together and the operator answers some and declines others
- **THEN** each question's outcome is reported individually
