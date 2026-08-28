# agent-conversation-workspace — delta

## ADDED Requirements

### Requirement: A request refused for good is answered as refused

A request that submits input to an agent SHALL be answered as a failure, carrying the refused
condition's own status and its own sentence, where the system determines while handling it that the
input cannot be delivered for a reason that cannot clear on its own.

It SHALL NOT answer such a request as accepted. An acknowledgement that carries the refusal inside
a field named for waiting, under a flag saying the request succeeded, tells the operator the
opposite of what happened, and is worse than no explanation: the operator has been given a reason
to wait for something that will never occur.

The refusal's status SHALL be the one the refused condition already carries, so that conditions the
system distinguishes — a request forbidden to this agent, a target in the wrong state, a runner with
no implementation — remain distinguishable to the caller. A single flattened status would discard
distinctions the system has already made correctly.

A refusal that cannot clear on its own SHALL be distinguished from one that can. Input waiting for a
turn in flight, a queue another request has already drained, or a budget that will reset is not a
failure, and answering those as failures would report working behaviour as broken.

#### Scenario: A permanently refused submission answers with the refusal

- **WHEN** an operator submits input to an agent
- **AND** the system determines the input cannot be delivered for a reason that cannot clear on its own
- **THEN** the request is answered as a failure
- **AND** the answer carries the refused condition's own status
- **AND** the answer carries the refusal's own sentence

#### Scenario: A submission that merely has to wait is still accepted

- **WHEN** an operator submits input to an agent
- **AND** delivery is deferred for a reason that can clear on its own
- **THEN** the request is answered as accepted
- **AND** the answer states what the input is waiting for

#### Scenario: A submission delivered by a concurrent drain is not reported as failed

- **WHEN** an operator submits input to an agent
- **AND** another delivery in progress takes that input before this request examines the queue
- **THEN** the request is answered as accepted

### Requirement: A refusal is reported only to the input it is about

Where the system refuses to start a turn, it SHALL attribute that refusal to the specific inputs the
refused turn would have carried, and SHALL report it only to a request that submitted one of them.

An agent's queue may hold input from several conversations, and the turn the system attempts is
built from the oldest eligible input, which is not necessarily the input the current request just
submitted. A refusal reported to whichever request happened to arrive describes a conversation the
caller did not ask about, cannot act on, and may not be permitted to see.

Where a request's own input was not part of the refused turn, the system SHALL report that the input
is waiting behind other input rather than repeating a refusal about it.

#### Scenario: A refusal about another conversation is not reported as this request's reason

- **WHEN** an operator submits input to an agent
- **AND** the system refuses a turn it was building from an older input belonging to another conversation
- **THEN** this request is answered as accepted
- **AND** the answer states that the input is waiting behind other input
- **AND** the answer does not carry the other conversation's refusal

### Requirement: Input refused for good does not stay queued for retry

Input SHALL NOT remain queued for further delivery attempts where the request that submitted it
has been answered with a refusal that cannot clear on its own.

Retrying is pointless where the system has already determined the reason cannot clear, and it is
worse than pointless once the operator has been told synchronously that the request failed: the
input goes on working behind them, and the report that the system gave up arrives later for a
request that already reported failure.

#### Scenario: The queue agrees with the answer the operator was given

- **WHEN** a request is answered with a refusal that cannot clear on its own
- **THEN** the input that request submitted is no longer queued for delivery
- **AND** the record of why it will not be delivered names the refusal

### Requirement: The operator reads why a submission was refused

Where a submission is answered with a refusal, the interface SHALL present the refusal's own
sentence to the operator.

Presenting only that a request failed, or only its status, replaces a wrong explanation with no
explanation. The operator's ability to see the stated reason is the outcome this behaviour exists
to produce; a correct status code that reaches a message the operator cannot read has not produced
it.

#### Scenario: A refused submission shows its reason

- **WHEN** a submission to an agent is refused
- **THEN** the operator is shown the refusal's own sentence
