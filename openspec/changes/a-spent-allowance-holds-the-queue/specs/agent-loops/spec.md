## MODIFIED Requirements

### Requirement: A firing is refused while its loop's agent is already running

The Hub SHALL refuse a firing whose loop agent already has a running turn, before that firing claims
a task or queues any input. A loop's agent runs one turn at a time.

Where the loop's agent's queue is held by a refusal of the provider's usage allowance and no other
agent in the project is free, the Hub SHALL refuse the firing in the same way. An agent whose queue
is held cannot take a turn until the hold ends, so a briefing queued for it is as stale by the time
it is read as one queued during a running turn. The hold is the one `agent-conversation-workspace`
defines, so this refusal and the scheduler cannot disagree about whether the agent can take a turn.

This requirement does not state which agent a firing staffs when another agent in the project is
free. `agent-flows` governs that.

Where the loop's summary reports why the loop is not proceeding, and this refusal would refuse the
loop's next firing, the summary SHALL report this refusal's reason. It SHALL NOT report a stalled
queue with no claimable task, since the next firing is refused before it looks at the queue.

The loop's job SHALL remain enabled and remain scheduled, so that a later firing proceeds once the
agent is free.

#### Scenario: A firing during a live turn queues nothing

- **WHEN** a loop's agent has a running turn and the loop's job fires
- **THEN** the firing is refused
- **AND** no inbound queue entry is created for that agent

#### Scenario: Repeated firings during one turn do not accumulate work

- **WHEN** a loop's job fires several times while its agent's single turn is running
- **THEN** the number of inbound queue entries created by those firings is zero

#### Scenario: A firing while the agent is held queues nothing

- **WHEN** a loop's agent's queue is held by an allowance refusal, no other agent in the project is free, and the loop's job fires
- **THEN** the firing is refused
- **AND** no inbound queue entry is created for that agent

#### Scenario: The loop's summary names the hold rather than a stall

- **WHEN** a loop's agent's queue is held, no other agent in the project is free, and the loop has one pending unassigned task
- **THEN** the loop's summary reports the hold as the reason it is not proceeding
- **AND** it does not report that no task is claimable

#### Scenario: The loop proceeds once the agent is free

- **WHEN** a loop's agent finishes its turn and the loop's job fires again with claimable work
- **THEN** the firing proceeds and claims a task

#### Scenario: The loop proceeds once the hold ends

- **WHEN** a loop's agent's hold has ended and the loop's job fires with claimable work
- **THEN** the firing proceeds and claims a task

## ADDED Requirements

### Requirement: A job firing into a held queue is coalesced

The Hub SHALL record a firing of a job that is not a loop as skipped, queuing nothing, when the job's agent's queue is held by a refusal of the provider's usage allowance and an earlier firing of the same job still has input queued for that agent.

A job's message is a standing instruction, still true when the agent can take it, which is why a
firing during a running turn queues its input rather than being refused. A hold can last hours, or
days, so queuing every firing would deliver the same instruction once per tick when the hold ends.
One queued copy delivers the instruction and the rest add nothing.

A firing when no earlier firing's input is queued SHALL queue as it does today, so an instruction is
never lost to the hold.

Consecutive skipped firings with the same reason SHALL be recorded as one row with a count, as a
loop's repeated stall is.

The reason recorded SHALL name the agent, the time the hold ends, and that an earlier firing's input
is still queued, and SHALL fit the firing record's summary field whole.

#### Scenario: The first firing during a hold queues

- **WHEN** a job's agent's queue is held and no earlier firing of the job has input queued
- **AND** the job fires
- **THEN** the firing queues its input

#### Scenario: Later firings during the hold add nothing

- **WHEN** a job's agent's queue is held and an earlier firing of the job has input queued
- **AND** the job fires three more times
- **THEN** no further input is queued for the agent
- **AND** one skipped firing record carries the three ticks

#### Scenario: One copy is delivered at the reset

- **WHEN** the hold ends
- **THEN** the job's instruction is delivered to the agent once

### Requirement: Pressing Run on a loop that declines names why it declined

The Hub SHALL answer an operator's manual firing of a loop that the loop's busy guard refused with a conflict that names the reason the guard gave, and SHALL NOT answer it as a failure to fire.

The busy guard refuses a firing when the job's agent is running a turn or its queue is held, and no
other agent in the project is free. It records nothing, deliberately, so there is no firing record
to read a reason from, and the most recent record is some earlier firing's.

The route SHALL answer from a firing record only when the manual firing wrote that record. Where it
wrote none, the route SHALL ask the guard again before anything else, because the guard is the
first question the firing asked, and SHALL answer a refusal with the guard's reason. A record some
earlier firing wrote is not this firing's answer, and the route SHALL NOT change that record's
requester to whoever pressed Run.

Where the firing declined because every task on the queue is in flight, and an agent those tasks are
staffed to is held, the answer SHALL name that agent and the time its hold ends. It SHALL NOT state
that the work is already being worked, or that nothing is wrong. The work is staffed, but it cannot
start until the hold ends.

#### Scenario: Run while the loop's agent is mid-turn and nobody else is free

- **WHEN** a loop's agent is running a turn, no other agent in the project is free, and the operator presses Run
- **THEN** the answer is a conflict naming the agent that is running
- **AND** it is not a server error reading "Failed to fire job"

#### Scenario: Run while the loop's agent is held

- **WHEN** a loop's agent's queue is held, no other agent in the project is free, and the operator presses Run
- **THEN** the answer is a conflict naming the agent and the time its hold ends

#### Scenario: Run on a flow whose in-flight work waits on a hold

- **WHEN** every task on a flow's queue is in flight, one of them is staffed to a held agent, and the operator presses Run
- **THEN** the answer names that agent and the time its hold ends
- **AND** it does not state that the work is already being worked, or that nothing is wrong

#### Scenario: A firing that recorded its own refusal is answered from that record

- **WHEN** the operator presses Run on a loop, the firing records a skipped firing with its reason, and the loop's agent has become busy since
- **THEN** the answer is a conflict carrying the recorded reason, not the busy guard's

#### Scenario: An earlier firing's record is not attributed to the press

- **WHEN** Run is pressed on a loop and the firing writes no record
- **THEN** no earlier firing's record has its requester changed
