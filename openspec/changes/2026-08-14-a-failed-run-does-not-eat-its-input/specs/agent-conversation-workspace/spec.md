# agent-conversation-workspace

## MODIFIED Requirements

### Requirement: Repeated delivery failure does not wedge an agent

The system SHALL return a failed run's input to the queue however that run failed, SHALL count how many times a queued input has failed to be delivered, and SHALL stop retrying it before it can block an agent indefinitely.

When a run fails before it completes, the input it was carrying returns to the queue so nothing is
lost. This SHALL hold for every abnormal ending, not only for those where the runtime never started.
A runtime that dies once the turn is under way is the failure most likely to occur, and returning
input only for the failures that happen earlier means the operator's message is consumed, never
retried, never given up on, and never reported — indistinguishable from never having been sent.

A run the operator deliberately stopped SHALL NOT return its input. The operator stopped the turn
knowing what it was carrying.

A returned input keeps its place in the queue and its binding to the conversation it arrived on, and
the queue is served in arrival order — so an input whose delivery kills the runtime is served again
immediately, and every later input, including a request to start a fresh conversation, waits behind
the one doing the killing. Nothing distinguishes an input returned five times from one that has
never been tried.

After repeated failure the system SHALL stop resuming the conversation's existing provider session
and start a new one, so that a provider session which cannot be resumed does not make the input
undeliverable forever.

After further failure the system SHALL stop attempting delivery, record why it gave up, and report
it to the operator. Retrying without limit is indistinguishable from being stuck, and an agent that
never accepts new input is worse than a message that was dropped loudly.

An input the system has given up on SHALL still name the run that was carrying it, so the operator
can find what happened to their message.

An input that is still being retried SHALL remain bound to its conversation. An input belonging to
no conversation cannot be scheduled at all, which would replace a visible wedge with a silent one.

Returning an input to the queue SHALL cause the system to attempt its delivery again without
requiring any further operator action. A limit on attempts protects nobody if nothing consumes the
attempts; an input left queued until an unrelated request happens to drain it is retried by
coincidence rather than by design.

Where a run's input has been returned, the system SHALL NOT report that run as having abandoned the
work it was bound to. The work is about to be handed to another run, so nothing has been dropped.

Where nothing else explains why an agent is not working, the wait SHALL be reported in terms of the
failed attempts.

#### Scenario: A returned input counts the attempt

- **WHEN** a run fails and its input returns to the queue
- **THEN** the input records that a delivery attempt failed

#### Scenario: A runtime that dies mid-turn returns its input

- **WHEN** a run's runtime ends abnormally after the turn has begun
- **THEN** the input it was carrying returns to the queue
- **AND** the attempt is counted

#### Scenario: A completed run keeps its input

- **WHEN** a run completes
- **THEN** its input is not returned to the queue

#### Scenario: A stopped run keeps its input

- **WHEN** the operator stops a run
- **THEN** its input is not returned to the queue

#### Scenario: A conversation that cannot be resumed is started afresh

- **WHEN** an input has failed to be delivered twice
- **THEN** the next delivery starts a new provider session rather than resuming the old one

#### Scenario: The system gives up and says so

- **WHEN** an input has failed to be delivered three times
- **THEN** it is no longer delivered
- **AND** the reason it was given up on is recorded
- **AND** the operator is told

#### Scenario: Giving up unblocks the agent

- **WHEN** an input the system has given up on was blocking the queue
- **THEN** a later input for the same agent is delivered

#### Scenario: A dropped input names the run that was carrying it

- **WHEN** the system gives up on an input
- **THEN** the record still names the run it was last delivered to

#### Scenario: A returned input is retried without being asked for

- **WHEN** a run fails and its input returns to the queue
- **THEN** the system attempts to deliver it again
- **AND** no operator action is required to make that happen

#### Scenario: A run whose input was returned is not reported as abandoning its work

- **WHEN** a run bound to a task fails and its input returns to the queue
- **THEN** the run is not reported as having left that task's work behind

#### Scenario: A run that dropped its input is still reported

- **WHEN** a run bound to a task fails and none of its input returns to the queue
- **THEN** the run is reported as having left that task's work behind

## ADDED Requirements

### Requirement: A re-delivered turn says the earlier attempt was cut off

Input delivered to an agent after an earlier delivery failed SHALL say so, naming which attempt this is.

An agent handed the same instruction a second time has no way to tell that it is a second time. It
may find its own half-finished work in the checkout and read it as someone else's, or repeat work
that is already done, or treat a partial state as the starting state. The system knows the attempt
count and the agent does not, and the cost of that asymmetry is paid in wasted turns.

What to do about half-finished work SHALL be left to the agent. It depends on what the work was, and
a general instruction to check or to redo would be wrong often enough to be worse than the bare fact.

Input on its first delivery SHALL carry no such note, so that the ordinary case is unchanged.

#### Scenario: A second delivery is announced as one

- **WHEN** input is delivered to an agent after one failed attempt
- **THEN** the delivered turn states that an earlier attempt did not finish
- **AND** it names which attempt this is

#### Scenario: A first delivery is unchanged

- **WHEN** input is delivered to an agent for the first time
- **THEN** the delivered turn says nothing about earlier attempts

#### Scenario: Only the retried input is annotated

- **WHEN** a turn carries both a retried input and one never tried before
- **THEN** only the retried one states that an earlier attempt did not finish
