## MODIFIED Requirements

### Requirement: A firing is refused while its loop's agent is already running

The Hub SHALL refuse a firing whose loop agent already has a running turn, or whose queue is held by a refusal of the provider's usage allowance, before that firing claims a task or queues any input. A loop's agent runs one turn at a time.

An agent whose queue is held cannot take a turn until the hold ends, so a briefing queued for it is
as stale by the time it is read as one queued during a running turn. The hold is the one
`agent-conversation-workspace` defines, so this refusal and the scheduler cannot disagree about
whether the agent can take a turn.

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

- **WHEN** a loop's agent's queue is held by an allowance refusal and the loop's job fires
- **THEN** the firing is refused
- **AND** no inbound queue entry is created for that agent

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
