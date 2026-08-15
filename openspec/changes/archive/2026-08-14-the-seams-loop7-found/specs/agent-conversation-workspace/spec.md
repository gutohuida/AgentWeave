# agent-conversation-workspace

## ADDED Requirements

### Requirement: Repeated delivery failure does not wedge an agent

The system SHALL count how many times a queued input has failed to be delivered, and SHALL stop retrying it before it can block an agent indefinitely.

When a run fails before it completes, the input it was carrying returns to the queue so nothing is
lost. That input keeps its place in the queue and its binding to the conversation it arrived on, and
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

Where nothing else explains why an agent is not working, the wait SHALL be reported in terms of the
failed attempts.

#### Scenario: A returned input counts the attempt

- **WHEN** a run fails and its input returns to the queue
- **THEN** the input records that a delivery attempt failed

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
