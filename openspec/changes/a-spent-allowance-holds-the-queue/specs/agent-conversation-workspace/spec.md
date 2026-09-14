## MODIFIED Requirements

### Requirement: Repeated delivery failure does not wedge an agent

The system SHALL return a failed run's input to the queue however that run failed, SHALL count how many times a queued input has failed to be delivered, and SHALL stop retrying it before it can block an agent indefinitely, except that a turn the provider's usage allowance refused SHALL NOT be counted as a failed delivery.

When a run fails before it completes, the input it was carrying returns to the queue so nothing is
lost. This SHALL hold for every abnormal ending, not only for those where the runtime never started.
A runtime that dies once the turn is under way is the failure most likely to occur, and returning
input only for the failures that happen earlier means the operator's message is consumed, never
retried, never given up on, and never reported — indistinguishable from never having been sent.

A run the operator deliberately stopped SHALL NOT return its input. The operator stopped the turn
knowing what it was carrying.

A run failed because the runtime reported a different provider session than the one the conversation
is bound to SHALL NOT return its input either. That failure is raised after the turn has run: the
work was done and its output delivered, so the input was processed rather than lost, and handing it
back would make the agent repeat a completed turn. Returning it would also defeat the check that
raised it — repeated failure gives up the conversation's provider session, so a later attempt would
adopt the very session the check refused, and a runtime that reports the wrong session would
overwrite the binding by being retried.

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

A run the provider refused because the agent's usage allowance is spent, with a stated time at
which it resets, SHALL return its input without counting a failed delivery, SHALL NOT give up the
conversation's provider session, and SHALL NOT give up the input. Those limits separate a session
that cannot be resumed from an input that cannot be served, and a spent allowance is neither: the
session and the input are both sound, and the provider has said when it will serve them. The
refusal SHALL still be recorded on the input, as a count distinct from failed deliveries.

A refusal whose stated reset time is not later than the refusal itself states no wait with an end.
It SHALL be counted as a failed delivery, so the limits above still bound it, and a provider that
keeps reporting a reset already past is given up on as any other repeated failure is.

An input the system has given up on SHALL still name the run that was carrying it, so the operator
can find what happened to their message.

An input that is still being retried SHALL remain bound to its conversation. An input belonging to
no conversation cannot be scheduled at all, which would replace a visible wedge with a silent one.

Returning an input to the queue SHALL cause the system to attempt its delivery again without
requiring any further operator action. A limit on attempts protects nobody if nothing consumes the
attempts; an input left queued until an unrelated request happens to drain it is retried by
coincidence rather than by design. An input returned by an allowance refusal is attempted again
when the agent's hold ends, as the requirement on held queues states.

Where a run's input has been returned, the system SHALL NOT report that run as having abandoned the
work it was bound to. The work is about to be handed to another run, so nothing has been dropped.

Where nothing else explains why an agent is not working, the wait SHALL be reported in terms of the
failed attempts.

#### Scenario: A returned input counts the attempt

- **WHEN** a run fails and its input returns to the queue
- **AND** the provider did not refuse the run for a spent allowance
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

#### Scenario: A run failed over its provider session keeps its input

- **WHEN** a run fails because the runtime reported a different provider session than the one bound
- **THEN** its input is not returned to the queue
- **AND** the conversation's binding is unchanged

#### Scenario: A conversation that cannot be resumed is started afresh

- **WHEN** an input has failed to be delivered twice
- **THEN** the next delivery starts a new provider session rather than resuming the old one

#### Scenario: The system gives up and says so

- **WHEN** an input has failed to be delivered three times
- **THEN** it is no longer delivered
- **AND** the reason it was given up on is recorded
- **AND** the operator is told

#### Scenario: A refused turn is not a failed delivery

- **WHEN** a run fails and the provider's reading for that turn says the allowance is refused, with a reset time
- **THEN** its input returns to the queue
- **AND** the input's failed-delivery count is unchanged
- **AND** the input records one more allowance refusal

#### Scenario: Refusals never give up the session or the input

- **WHEN** an input's delivery is refused by the allowance three times in a row
- **THEN** the conversation's provider session is still bound
- **AND** the input is still queued

#### Scenario: A refusal with no reset time is counted as today

- **WHEN** a run fails and the provider's reading says the allowance is refused but states no reset time
- **THEN** the input records that a delivery attempt failed

#### Scenario: A refusal whose reset time has already passed is counted

- **WHEN** a run fails and the provider's reading says the allowance is refused with a reset time no later than the refusal
- **THEN** the input records that a delivery attempt failed
- **AND** repeated such refusals give up the input as any repeated failure does

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

### Requirement: A re-delivered turn says the earlier attempt was cut off

Input delivered to an agent after an earlier delivery failed or was refused by the provider's allowance SHALL say so, naming which attempt this is.

An agent handed the same instruction a second time has no way to tell that it is a second time. It
may find its own half-finished work in the checkout and read it as someone else's, or repeat work
that is already done, or treat a partial state as the starting state. The system knows the attempt
count and the agent does not, and the cost of that asymmetry is paid in wasted turns.

A delivery the provider refused for a spent allowance is an earlier attempt for this purpose. It
was cut off before the turn began or part-way through it, and the attempt named SHALL count it
alongside failed deliveries.

What to do about half-finished work SHALL be left to the agent. It depends on what the work was, and
a general instruction to check or to redo would be wrong often enough to be worse than the bare fact.

Input on its first delivery SHALL carry no such note, so that the ordinary case is unchanged.

#### Scenario: A second delivery is announced as one

- **WHEN** input is delivered to an agent after one failed attempt
- **THEN** the delivered turn states that an earlier attempt did not finish
- **AND** it names which attempt this is

#### Scenario: A delivery after a refusal is announced as one

- **WHEN** input is delivered to an agent after one delivery the provider's allowance refused
- **THEN** the delivered turn states that an earlier attempt did not finish
- **AND** it names attempt 2

#### Scenario: A first delivery is unchanged

- **WHEN** input is delivered to an agent for the first time
- **THEN** the delivered turn says nothing about earlier attempts

#### Scenario: Only the retried input is annotated

- **WHEN** a turn carries both a retried input and one never tried before
- **THEN** only the retried one states that an earlier attempt did not finish

## ADDED Requirements

### Requirement: A turn the provider's allowance refused holds the agent's queue until the reset

The system SHALL hold an agent's queue, starting no turn for input from agents or jobs, while the provider's most recent word about that agent is a refusal of its usage allowance and the refusal's reset time has not passed.

The provider's most recent word is the newest turn outcome for the agent that says something about
the provider: a reading of the allowance, or a turn in which the provider served tokens. An outcome
that says nothing about the provider, such as a runtime that never started or a run the Hub found
dead at startup, SHALL NOT end a hold.

The hold SHALL last at least one minute after the refusal, whatever reset time the refusal states,
so that a reset time already in the past cannot become a cycle of refused turns.

The hold SHALL be derived from recorded turn outcomes rather than stored separately, so that it
survives a restart of the Hub and ends by itself when any later turn is served.

Input from the operator that arrived after the refusal SHALL let one turn start despite the hold.
Only the operator can change the allowance, by enabling overage, adding credit or binding the agent
to another runner, and a hold derived from the provider's last word cannot see that it has changed.
The turn that starts is the one the queue would ordinarily start. If the provider refuses it too,
that refusal renews the hold, and input that arrived before it cannot start another.

When the reset time passes, the system SHALL attempt the agent's queue again without any operator
action. That includes a reset that passed while the Hub was not running, and a hold that began
with a turn which ended in some way other than failing, since the hold follows the provider's
reading rather than how the turn ended.

While the queue is held, the system SHALL report the hold as the reason the agent is waiting,
naming the time it ends, and SHALL record an operator-visible event each time a refusal starts or
renews a hold. Once the hold has ended, the system SHALL NOT report it as a reason for any input,
including input the refusal returned.

A job firing whose input waits on a held queue SHALL be reported as still in progress, not as
failed. That includes the firing whose own turn the provider refused, and a held firing across a
restart of the Hub. Its input is waiting for a stated time, not refused, and the delivery at the
reset is what ends the firing.

#### Scenario: A refused turn holds the queue

- **WHEN** an agent's turn is refused by the allowance with a reset time an hour away
- **AND** another agent sends it a message
- **THEN** no turn starts for the agent before the reset time
- **AND** the message is still queued

#### Scenario: The queue drains at the reset

- **WHEN** an agent's queue is held and the reset time passes
- **THEN** a turn starts for the agent without any operator action

#### Scenario: A reset that passed while the Hub was down still drains

- **WHEN** an agent's queue is held, the Hub stops, and it starts again after the reset time
- **THEN** a turn starts for the agent once the Hub is serving requests

#### Scenario: A reset time in the past does not spin

- **WHEN** a turn is refused by the allowance with a reset time already past
- **THEN** no turn starts for the agent for at least one minute after the refusal

#### Scenario: An outcome that says nothing about the provider does not end the hold

- **WHEN** an agent's queue is held and the Hub records a run for it that never started its runtime
- **THEN** the queue is still held

#### Scenario: A served turn ends the hold

- **WHEN** an agent's queue is held and a turn for it is served by the provider
- **THEN** the queue is no longer held

#### Scenario: New operator input probes once

- **WHEN** an agent's queue is held and the operator sends it a message
- **THEN** one turn starts for the agent
- **AND** if the provider refuses that turn, no further turn starts before the new reset time

#### Scenario: The hold is reported with its end

- **WHEN** an agent's queue is held
- **THEN** the agent's queue status names the hold as the reason it is waiting, and the time the hold ends
- **AND** an event recording the hold was persisted when the refusal arrived

#### Scenario: A job firing into a held queue stays in progress

- **WHEN** a job's firing queues input for an agent whose queue is held
- **THEN** the firing is recorded as in progress, not failed

#### Scenario: A firing whose own turn was refused ends with its delivery

- **WHEN** a job's firing starts a turn and the provider's allowance refuses it
- **THEN** the firing is recorded as in progress, not failed
- **AND** when its input is delivered after the reset, the firing takes that turn's outcome

#### Scenario: A held firing survives a restart

- **WHEN** a job's firing is waiting on a held queue and the Hub restarts
- **THEN** the firing is still recorded as in progress

#### Scenario: A hold that began with a completed turn still wakes

- **WHEN** a turn completes but the provider's reading for it says the allowance is refused, with a reset time
- **THEN** the agent's queue is held
- **AND** a turn starts for the agent at the reset without any operator action

#### Scenario: An ended hold is not reported

- **WHEN** an agent's hold has ended and input the refusal returned is still queued
- **THEN** the agent's queue status does not name the hold as the reason it is waiting
