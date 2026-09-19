## MODIFIED Requirements

### Requirement: A firing is refused while its loop's agent is already running

The Hub SHALL refuse a firing whose loop agent already has a running turn, before that firing claims
a task or queues any input. A loop's agent runs one turn at a time.

Where the loop's agent's queue is held by a refusal of the provider's usage allowance, the Hub SHALL
refuse the firing in the same way. An agent whose queue is held cannot take a turn until the hold
ends, so a briefing queued for it is as stale by the time it is read as one queued during a running
turn. The hold is the one `agent-conversation-workspace` defines, so this refusal and the scheduler
cannot disagree about whether the agent can take a turn.

**For a loop that declares no specification document, neither refusal SHALL depend on whether any
other agent in the project is free.** Such a loop staffs only the agent its job names
(`agent-flows`), so another agent being free changes nothing about what the firing could do. For a
flow, both refusals apply where no other agent in the project is free, since a flow may staff any
available agent.

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

**Where a refusal is reported to the operator, its stated reason SHALL be true of the loop it
refused.** A refusal of a loop that declares no specification document SHALL NOT be reported as no
other agent being free, since another agent may well be free and freeing one more would change
nothing. It SHALL instead state that the loop runs only the agent its job names.

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

#### Scenario: A documentless loop is refused while another agent is free

- **WHEN** a loop declares no specification document, its agent has a running turn, another agent in
  the project is free, the loop's queue holds a pending task, and the loop's job fires
- **THEN** the firing is refused
- **AND** no inbound queue entry is created for any agent
- **AND** the loop's execution history gains no entry from that firing

#### Scenario: A documentless loop is refused while another agent is free and its own agent is held

- **WHEN** a loop declares no specification document, its agent's queue is held by an allowance
  refusal, another agent in the project is free, the loop's queue holds a pending task, and the
  loop's job fires
- **THEN** the firing is refused
- **AND** no inbound queue entry is created for any agent

#### Scenario: A flow is not refused while another agent is free

- **WHEN** a loop declares a specification document, its job's agent has a running turn, another
  agent in the project is free, and the loop's queue holds a startable task
- **THEN** the firing is not refused
- **AND** the free agent is started for that task

#### Scenario: The refusal of a documentless loop does not blame a busy roster

- **WHEN** a loop declares no specification document, its agent has a running turn, another agent in
  the project is free, and the operator fires the loop's job by hand
- **THEN** the refusal states that the loop runs only the agent its job names
- **AND** it does not state that no other agent is free

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
