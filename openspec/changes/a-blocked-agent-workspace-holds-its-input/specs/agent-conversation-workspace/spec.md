## MODIFIED Requirements

### Requirement: A delivery attempt is counted only where a delivery was attempted

The system SHALL NOT count a delivery attempt against queued input where nothing was delivered and
the reason nothing was delivered prevents the agent from running at all.

Input refused for a reason that prevents the agent from running **at all** SHALL NOT have a delivery
attempt counted against it, and SHALL NOT be given up on for that reason. No delivery was attempted:
the refusal was raised before anything carried it anywhere, and while the reason holds no other
input for that agent could have run in its place either, so giving up on this input buys nothing.
Counting it means the operator's own activity — sending another message, or asking the system to
start the work already waiting — consumes the allowance that exists to detect repeated failure, and
destroys input that nothing ever tried to deliver.

This SHALL NOT extend to a refusal that prevents only this input from being delivered. Where other
queued input could have run, the input at the head of the queue is in the way, and the system SHALL
go on counting its attempts and SHALL still give up on it at the limit.

A refusal to prepare **the agent's own workspace** SHALL be answered by that same question rather
than assumed either way. The agent's workspace carries every turn of that agent that does not have a
workspace of its own, so a workspace that cannot be prepared blocks that entire population and is a
condition only the operator can clear — the same shape as an agent with no runner bound, which is
held. So where the agent has other queued input that would have run **somewhere else**, the head of
the queue is in the way and SHALL keep counting; where it has none, nothing is starving behind that
input and it SHALL be held for the repair.

Whether other queued input would have run somewhere else SHALL be decided by where that input would
actually have executed, and SHALL NOT be inferred from the input naming a task. Not every turn about
a task gets a checkout of its own: work on a task the system never gave one to runs in the agent's
own workspace, as does work naming a task that no longer takes new work. Input like that is blocked
by the same obstruction, so giving up on the head of the queue releases nothing and SHALL NOT be
treated as evidence that something else could have run. Where the answer is uncertain, the system
SHALL hold the input rather than count against it: holding a message the queue could have released
delays it, and counting one it could not destroys it.

A refusal to prepare **a task's own checkout** SHALL keep counting. That workspace belongs to one
task, other input for the agent runs elsewhere, and the refused input really is in the way.

Where the system gives up on input, the reason it records SHALL describe what actually happened to
that input. Input that was never carried anywhere has not failed to be delivered.

#### Scenario: Sending more input does not consume the earlier input's allowance

- **WHEN** an operator submits input to an agent whose environment is not ready
- **AND** the operator submits further input to the same agent
- **THEN** no delivery attempt is counted against the earlier input
- **AND** the earlier input remains queued

#### Scenario: The input is still there when the agent becomes able to run

- **WHEN** input has been waiting for an agent that cannot run at all
- **AND** the operator has submitted further input and asked the system to start the waiting work
- **AND** the operator then makes the agent able to run
- **THEN** every input they submitted is delivered
- **AND** none of it was discarded while they were making the agent able to run

#### Scenario: Asking the system to start waiting work does not destroy it

- **WHEN** input is waiting for an agent whose environment is not ready
- **AND** the operator asks the system to start the waiting work without submitting anything new
- **THEN** no delivery attempt is counted against that input
- **AND** the input remains queued

#### Scenario: Unrelated activity does not consume it either

- **WHEN** input is waiting for an agent whose environment is not ready
- **AND** another agent's turn ends, causing every queued agent to be re-evaluated
- **THEN** no delivery attempt is counted against that input

#### Scenario: A run that carried the input and failed still counts

- **WHEN** a run carrying queued input fails
- **THEN** a delivery attempt is counted against that input
- **AND** the existing limit still applies to it

#### Scenario: A refusal about what was asked still counts

- **WHEN** a turn is refused because of what the queued input asked for
- **THEN** a delivery attempt is counted against that input
- **AND** the existing limit still applies to it

#### Scenario: A refusal that blocks only this input still counts

- **WHEN** a turn is refused for a reason that would not prevent the agent's other queued input from
  being delivered
- **THEN** a delivery attempt is counted against that input
- **AND** the existing limit still applies to it, so it cannot hold the queue indefinitely

#### Scenario: A blocked agent workspace holds input that nothing else was waiting behind

- **WHEN** an agent's own workspace cannot be prepared
- **AND** every other input queued for that agent would have run in that same workspace
- **THEN** no delivery attempt is counted against the input at the head of the queue
- **AND** it is still queued after repeated attempts to start the agent
- **AND** it is delivered once the operator clears the condition

#### Scenario: A blocked agent workspace does not hold input that something else was waiting behind

- **WHEN** an agent's own workspace cannot be prepared
- **AND** other input queued for that agent is about a task that has a checkout of its own, so it
  would run there
- **THEN** a delivery attempt is counted against the input at the head of the queue
- **AND** the existing limit still applies to it, so it cannot hold the other input indefinitely

#### Scenario: Input about a task that has no checkout of its own is not something else that could have run

- **WHEN** an agent's own workspace cannot be prepared
- **AND** the only other input queued for that agent is about a task whose work executes in the
  agent's own workspace rather than in a checkout of its own
- **THEN** no delivery attempt is counted against the input at the head of the queue
- **AND** it is still queued after repeated attempts to start the agent

#### Scenario: Input that could not have run for its own reasons does not count either

- **WHEN** an agent's own workspace cannot be prepared
- **AND** the only other input queued for that agent is input the system would not have started —
  because it names work that takes no new work, or because it is beyond the limits that decide what
  may start
- **THEN** no delivery attempt is counted against the input at the head of the queue
- **AND** it is still queued after repeated attempts to start the agent

#### Scenario: A blocked task checkout keeps counting

- **WHEN** the checkout for the task a turn is about cannot be prepared
- **THEN** a delivery attempt is counted against that input
- **AND** the existing limit still applies to it
