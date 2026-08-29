## ADDED Requirements

### Requirement: An action addressed to one conversation reports the conversation it actually started

A response reporting that a turn started SHALL name the conversation whose queued input that turn delivered, and SHALL NOT report a start against a conversation that did not start.

A turn is owned by the agent, not by the conversation: one agent runs one turn at a time, and the
queue it is drawn from is the agent's, ordered by arrival across every conversation that agent
holds. An action addressed to a single conversation therefore cannot promise that *that*
conversation will run. What it can promise, and SHALL, is to say which conversation did.

The addressed conversation's identifier SHALL still be returned, so a caller can correlate its
request with the response. It SHALL be carried in a field distinct from the started conversation's
identifier, because a single field serving both meanings is what allows a true value and a false
claim to be indistinguishable.

When nothing started, the response SHALL name no started conversation and SHALL state the reason.

The rule is about the report, not the selection. Which entry a turn is built from is out of scope
here and SHALL NOT be changed to satisfy this requirement: reordering the agent's queue so the
addressed conversation runs first would let a later-arriving entry overtake an earlier one at the
operator's keystroke.

#### Scenario: The started conversation is the one addressed

- **WHEN** a turn is started for a conversation and the agent's next eligible queued entry belongs to that same conversation
- **THEN** the response reports `started` as true
- **AND** the started conversation's identifier equals the addressed conversation's identifier

#### Scenario: The started conversation is a different one

- **WHEN** a turn is started for a conversation and the agent's next eligible queued entry belongs to a different conversation of the same agent
- **THEN** the response reports `started` as true
- **AND** the started conversation's identifier is that other conversation's identifier
- **AND** the addressed conversation's identifier is returned unchanged
- **AND** the two identifiers are readable as different values by the caller

#### Scenario: Nothing started

- **WHEN** a turn is requested for a conversation and no turn begins
- **THEN** the response reports `started` as false
- **AND** no started conversation identifier is reported
- **AND** a reason is stated

### Requirement: The operator is told when the turn that began is not the one they were watching

The interface offering the action SHALL distinguish a turn that began in the conversation on screen from one that began elsewhere, and SHALL name the other conversation when it is not the one on screen.

Reporting the same confirmation for both cases leaves the operator watching a conversation where
nothing will appear: no run, no output, no error. The next act available to them is to press the
control again, which starts a further turn they also did not ask for.

#### Scenario: The turn began in the conversation on screen

- **WHEN** the started conversation is the one displayed
- **THEN** the interface confirms that this conversation is continuing

#### Scenario: The turn began in another conversation

- **WHEN** the started conversation is not the one displayed
- **THEN** the interface states that a different conversation started
- **AND** identifies that conversation

#### Scenario: Nothing began

- **WHEN** no turn started
- **THEN** the interface states that nothing started
- **AND** gives the stated reason
