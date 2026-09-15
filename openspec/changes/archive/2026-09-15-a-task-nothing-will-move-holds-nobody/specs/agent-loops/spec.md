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

**Another agent being free SHALL NOT let a firing queue input for the loop's own agent while that
agent is running a turn or held.** Where the loop's queue holds no task in a non-terminal status,
there is nothing another agent could be given, and the only input the firing could queue is a
briefing for the busy agent to fill the queue. The Hub SHALL refuse that firing exactly as it
refuses one where nobody else is free: before it records anything or queues any input. A briefing
queued for a busy agent to fill an empty queue is as stale by the time it is read as any other, and
one queued per firing is the accumulation this requirement exists to stop.

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

#### Scenario: An empty queue is refused while its agent is busy, whoever else is free

- **WHEN** a loop's agent has a running turn, the loop's queue holds no task in a non-terminal status, another agent in the project is free, and the loop's job fires several times
- **THEN** every one of those firings is refused
- **AND** no inbound queue entry is created for the loop's agent
- **AND** the loop's execution history gains no entries from those firings

#### Scenario: An empty queue still fires its agent once the agent is free

- **WHEN** no task has ever named a loop, its agent is running no turn and is not held, and the loop's job fires
- **THEN** the firing proceeds and queues one briefing for the loop's agent

### Requirement: Pressing Run on a loop that declines names why it declined

The Hub SHALL answer an operator's manual firing of a loop that the loop's busy guard refused with a conflict that names the reason the guard gave, and SHALL NOT answer it as a failure to fire.

The busy guard refuses a firing when the job's agent is running a turn or its queue is held, and
either no other agent in the project is free or the loop's queue holds no task in a non-terminal
status. It records nothing, deliberately, so there is no firing record to read a reason from, and
the most recent record is some earlier firing's.

The answer SHALL say which of those two held. Stating that no other agent is free when one is free
tells the operator to free an agent, which would change nothing; what the loop lacks is work.

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

#### Scenario: Run while the loop's agent is mid-turn and its queue is empty

- **WHEN** a loop's agent is running a turn, the loop's queue holds no task in a non-terminal status, another agent in the project is free, and the operator presses Run
- **THEN** the answer is a conflict naming the agent that is running
- **AND** it does not state that no other agent is free
- **AND** no inbound queue entry is created for the loop's agent

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

