## MODIFIED Requirements

### Requirement: A review nobody is doing is named, whatever its history

Where a task is under review with an agent named on it and that agent is not working it, as `agent-loops` *A task reported as in flight is one an agent is actually working* defines, the flow SHALL surface that review, naming the task and the named agent, and SHALL do so regardless of how the task reached that state and regardless of whether any run has ever been bound to it.

This SHALL hold for a task no run has ever touched. A task an operator moved into review by hand has no run boundary to have diagnosed it, so the surfacing that answers a review turn ending without a verdict cannot reach it; the operator SHALL be told the same thing by the same words either way.

Input naming the task that is queued for some other agent SHALL NOT keep the review from being surfaced. A message a third agent is sent about the task is not the named agent reviewing it. Where input naming the task is queued for the named agent and its last delivery was refused, the surfaced sentence SHALL contain that refusal's own words, because it, not the absence of a turn, is why nothing is happening.

The surfaced sentence SHALL NOT state that no input is queued, because input the flow does not count may be.

Where the agent named on the task is the agent that produced its work, and some agent's turn on the task is running or waiting to be delivered, the flow's recovery of that task waits for the turn, and the task SHALL NOT be surfaced as a review that agent is not doing. Such an agent is not reviewing it, and a sentence naming it as the reviewer would be false while the recovery is only waiting.

The flow SHALL NOT substitute another agent as part of this surfacing. Replacing a reviewer is governed by the resolution that already runs at a review turn's end, and a second path that also replaced one could reach a different answer than the first.

#### Scenario: An operator-walked review with no run is surfaced

- **WHEN** an operator moves a task to under review by hand, naming an agent, and no run is ever bound to that task
- **THEN** the flow surfaces that review, naming the task and that agent

#### Scenario: A surfaced review that was diagnosed at a run boundary stays surfaced

- **WHEN** a review turn ends without recording a verdict and the resolution finds no agent left to substitute
- **THEN** the task remains under review with the silent reviewer named
- **AND** the flow surfaces that review on each firing rather than reporting the queue as busy

#### Scenario: The surfacing names the agent, not only the task

- **WHEN** a review nobody is doing is surfaced
- **THEN** the sentence the operator reads names the agent whose name is on the task

#### Scenario: A third agent's message about the task does not hide the review

- **WHEN** a task is under review with an agent named on it, no turn is running on it, and a message naming the task is queued for a different agent
- **THEN** the flow surfaces that review, naming the task and the named agent

#### Scenario: A refused review delivery is surfaced with its refusal

- **WHEN** a task is under review with an agent named on it, and the review input queued for that agent was refused on its last delivery
- **THEN** the flow surfaces that review
- **AND** the sentence contains the refusal's own words

#### Scenario: An author left holding a review, while another agent's turn is on the task, is not named as its reviewer

- **WHEN** a task is under review with the agent that produced its work named on it, and a message naming the task is queued for a different agent
- **THEN** the flow reports the task as in flight and does not surface it as a review nobody is doing
- **AND** no sentence names the author as the task's reviewer

#### Scenario: No substitution happens on this path

- **WHEN** the flow surfaces a review nobody is doing
- **THEN** no other agent is fired for that review by this path
- **AND** the assignee on the task is not changed by it

### Requirement: A flow treats an agent whose queue is held as unable to take a turn

A flow SHALL treat an agent whose queue is held by a refusal of the provider's usage allowance as unable to take a turn, wherever a firing asks whether an agent can take one.

The hold is the one `agent-conversation-workspace` defines. The scheduler starts no turn for a held
agent's autonomous input, so a briefing queued for it is as stale by the time it is read as one
queued during a running turn. A flow that asked the question about running agents alone would
re-brief a held agent's assigned task on every firing, and the agent would find a stack of
identical briefings when its hold ended.

A task assigned to a held agent SHALL be reported as in flight while input naming that task is
queued for that agent, and SHALL NOT be briefed again. Input naming the task that is queued for a different agent does not count, and neither does input past the hop budget or input whose last delivery was refused, as `agent-loops` *A task reported as in flight is one an agent is actually working* defines. Where no input naming it is queued for the held agent, the firing
SHALL brief it once, as it resumes any assigned task, and the task is in flight from then on. A held agent is
working nothing, so its assignment alone is not the in-flight condition: that condition is the one
`agent-loops` *A task reported as in flight is one an agent is actually working* already states.

A held agent SHALL NOT be chosen as a firing's default agent, and SHALL NOT be recruited for new
work. A reviewer the task declares is unaffected: the declaration names who reviews, and the review
waits for the hold. A reviewer chosen by availability follows *A flow resolves a reviewer by
declaration, then by availability*.

Where a review cannot be staffed and an agent was passed over because its queue is held, the reason
surfaced SHALL name the hold among the grounds, and SHALL NOT state that every agent is running a
turn, holding work or excluded.

This concerns only whether an agent can take a turn now. Which tasks an agent holds, and which of
them make it unavailable, is unchanged.

#### Scenario: A held assignee whose briefing is queued is not re-briefed

- **WHEN** an agent's queue is held, it is assigned a task, input naming that task is queued for it, and another agent in the project is free
- **AND** the flow fires three times
- **THEN** no further input is queued for the held agent
- **AND** its task is reported in flight

#### Scenario: A held assignee with nothing queued is briefed once

- **WHEN** an agent's queue is held, it is assigned a task, and no input naming that task is queued
- **AND** the flow fires three times
- **THEN** exactly one input naming that task is queued for the agent

#### Scenario: A held job agent is passed over

- **WHEN** a flow's job agent is held and another agent is free
- **AND** an unassigned task is startable
- **THEN** the firing staffs the free agent, not the held one

#### Scenario: A held agent is not free

- **WHEN** an agent is held, running no turn and holding no task
- **THEN** it is not counted among the agents free for new work or for review

#### Scenario: An unstaffed review names the hold

- **WHEN** no reviewer is declared, and the only agent that could review a task is held, running no turn and holding no task
- **THEN** the flow surfaces that it could not staff the review
- **AND** the surfaced reason names the provider's usage limit among the grounds
