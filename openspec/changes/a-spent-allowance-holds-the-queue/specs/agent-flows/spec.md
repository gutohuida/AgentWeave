## ADDED Requirements

### Requirement: A flow treats an agent whose queue is held as unable to take a turn

A flow SHALL treat an agent whose queue is held by a refusal of the provider's usage allowance exactly as it treats an agent that is running a turn, wherever a firing asks whether an agent can take one.

The hold is the one `agent-conversation-workspace` defines. The scheduler starts no turn for a held
agent's autonomous input, so a briefing queued for it is as stale by the time it is read as one
queued during a running turn. A flow that asked the question about running agents alone would
re-brief a held agent's assigned task on every firing, and the agent would find a stack of
identical briefings when its hold ended.

A task already assigned to a held agent SHALL be reported as in flight and SHALL NOT be staffed
again. A held agent SHALL NOT be chosen as a firing's default agent, SHALL NOT be recruited for new
work, and SHALL NOT be selected as a reviewer by availability. A reviewer the task declares is
unaffected: the declaration names who reviews, and the review waits for the hold.

This concerns only whether an agent can take a turn now. Which tasks an agent holds, and which of
them make it unavailable, is unchanged.

#### Scenario: A held assignee is not re-briefed

- **WHEN** an agent's queue is held, it is assigned a task with its briefing queued, and another agent in the project is free
- **AND** the flow fires three times
- **THEN** no further input is queued for the held agent
- **AND** its task is reported in flight

#### Scenario: A held job agent is passed over

- **WHEN** a flow's job agent is held and another agent is free
- **AND** an unassigned task is startable
- **THEN** the firing staffs the free agent, not the held one

#### Scenario: A held agent is not free

- **WHEN** an agent is held, running no turn and holding no task
- **THEN** it is not counted among the agents free for new work or for review
