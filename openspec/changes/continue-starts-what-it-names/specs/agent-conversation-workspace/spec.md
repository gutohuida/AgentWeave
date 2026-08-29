## ADDED Requirements

### Requirement: A start is reported only to the input it is about

Where the system starts a turn in answer to a request naming one conversation, it SHALL report that request as started only where the started turn carried that conversation's input, and SHALL otherwise report that the input is waiting behind other input.

This is the start-direction counterpart of "A refusal is reported only to the input it is about",
and it exists for the same reason. An agent's queue may hold input from several conversations, and
the turn the system attempts is built from the oldest eligible input, which is not necessarily the
input the current request names. Reporting a start to whichever request happened to arrive describes
a turn in a conversation the caller did not ask about — and unlike a refusal, it is
indistinguishable from success, so the caller has no reason to look further. Someone watching the
conversation they named sees no run, no output and no error, and the next act available to them is
to ask again.

The response SHALL identify the conversation whose input the turn actually carried, so that a
request answered as waiting can be acted on rather than only retried.

Reporting SHALL NOT be corrected by changing which input is selected. The turn is the agent's and
its input is taken in arrival order; selecting a later input because a request names its
conversation would let that request overtake input that arrived first, and would leave a quiet
conversation waiting for as long as a busy one is asked about.

#### Scenario: The turn carried the named conversation's input

- **WHEN** a request names a conversation and the started turn carried that conversation's input
- **THEN** the request is answered as started
- **AND** the conversation identified as started is the one named

#### Scenario: The turn carried another conversation's input

- **WHEN** a request names a conversation and the started turn carried a different conversation's input
- **THEN** the request is not answered as started
- **AND** the answer states that the named conversation's input is waiting behind other input
- **AND** the answer identifies the conversation whose input the turn carried
- **AND** the named conversation's input remains queued

#### Scenario: No turn started

- **WHEN** a request names a conversation and no turn started
- **THEN** the request is not answered as started
- **AND** the answer states the reason no turn started
- **AND** no conversation is identified as started

#### Scenario: A diagnostic about a turn names the conversation the turn belongs to

- **WHEN** the system records that a turn did not start, in answer to an act addressed to one conversation
- **THEN** the record names the conversation the reason belongs to rather than the conversation addressed

### Requirement: The operator is told when the turn that began is not the one they asked for

The interface offering to start a conversation's queued work SHALL distinguish a turn that began in that conversation from one that began elsewhere, and SHALL identify the other conversation when it is not the one asked for.

Rendering the same confirmation for both outcomes leaves the operator watching a conversation where
nothing will appear. Because the control remains available, the act available to them is to press it
again, starting a further turn they did not ask for and did not observe.

#### Scenario: The turn began in the conversation on screen

- **WHEN** the started conversation is the one displayed
- **THEN** the interface confirms that this conversation is continuing

#### Scenario: The turn began in another conversation

- **WHEN** a turn began in a conversation other than the one displayed
- **THEN** the interface states that the displayed conversation's work is waiting behind other input
- **AND** identifies the conversation that began

#### Scenario: Nothing began

- **WHEN** no turn started
- **THEN** the interface states that nothing started
- **AND** gives the stated reason
