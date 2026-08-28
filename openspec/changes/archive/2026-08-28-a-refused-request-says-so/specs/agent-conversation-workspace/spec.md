# agent-conversation-workspace — delta

## ADDED Requirements

### Requirement: A request refused for what it asked is answered as refused

A request submitting input to an agent SHALL be answered as a failure, carrying the refused
condition's own status and its own sentence, where the system determines while handling it that the
input cannot be delivered because of what the request asked for.

It SHALL NOT answer such a request as accepted. An acknowledgement that carries the refusal inside
a field named for waiting, under a flag saying the request succeeded, tells the operator the
opposite of what happened, and is worse than no explanation: the operator has been given a reason
to wait for something that will never occur.

The refusal's status SHALL be the one the refused condition already carries, so that conditions the
system distinguishes — a request forbidden to this agent, a target in the wrong state, a runner with
no implementation — remain distinguishable to the caller. A single flattened status would discard
distinctions the system has already made correctly.

A refusal about **what was asked** SHALL be distinguished from a refusal about **the environment the
agent would run in**. The system deliberately accepts and holds input that cannot be delivered yet
because the environment is not ready — no runner is bound, the bound runner's program is not
installed, an isolated workspace could not be prepared — precisely so that repairing the environment
delivers it. Answering those as failures would discard input the system has promised to keep, and
would report as broken the behaviour that makes the repair worth performing. Input waiting for a turn
in flight, a queue another request has already drained, or a budget that will reset is likewise not
a failure.

#### Scenario: A submission refused for what it asked answers with the refusal

- **WHEN** an operator submits input to an agent
- **AND** the system determines the input cannot be delivered because of what the request asked for
- **THEN** the request is answered as a failure
- **AND** the answer carries the refused condition's own status
- **AND** the answer carries the refusal's own sentence

#### Scenario: A submission refused because the environment is not ready is still accepted

- **WHEN** an operator submits input to an agent
- **AND** delivery is refused because the environment the agent would run in is not ready
- **THEN** the request is answered as accepted
- **AND** the answer states the refusal's own sentence as what the input is waiting for
- **AND** the input remains queued, so that repairing the environment delivers it

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

### Requirement: Input refused for what it asked does not stay queued for retry

Input SHALL NOT remain queued for further delivery attempts where the request that submitted it has
been answered with a refusal about what that request asked for.

Retrying is pointless where nothing about the environment changing would alter the answer, and it is
worse than pointless once the operator has been told synchronously that the request failed: the
input goes on working behind them, and the report that the system gave up arrives later for a
request that already reported failure.

This SHALL NOT extend to input refused because the environment is not ready. That input stays queued
and keeps its existing delivery-attempt bookkeeping, because the repair that makes it deliverable is
exactly what the operator has been told to perform.

Input withdrawn this way SHALL NOT be reported as input the system gave up on after trying. Nothing
carried it — no turn was ever started for it — so there is no run for it to name and no attempt
count to report. The operator was told synchronously; a later report that the system stopped trying
would describe an effort that never happened.

Where the system has already told the operator that input is queued, and then withdraws it in the
same request, it SHALL report the withdrawal. An operator holding both an error and a queue that
still counts the input is being told two different things about one request, which is the same
failure this behaviour exists to remove.

#### Scenario: The queue agrees with the answer the operator was given

- **WHEN** a request is answered with a refusal about what that request asked for
- **THEN** the input that request submitted is no longer queued for delivery
- **AND** the record of why it will not be delivered names the refusal

#### Scenario: Input awaiting a repairable environment is still queued

- **WHEN** a request is answered as accepted because the environment the agent would run in is not ready
- **THEN** the input that request submitted remains queued for delivery

#### Scenario: The withdrawal is reported, and not as an abandonment

- **WHEN** a request is answered with a refusal about what that request asked for
- **AND** the system had already reported that request's input as queued
- **THEN** the system reports that the input has been withdrawn
- **AND** it does not report that it gave up on the input after failed delivery attempts

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
