## ADDED Requirements

### Requirement: A firing staffs a loop that declares no document only with the agent its job names

The Hub SHALL staff a task that has no assignee, in a loop that declares no specification document, only with the agent that loop's job names, and SHALL NOT select any other agent for it.

Where that agent cannot take a turn, the firing SHALL staff nobody for that task rather than
substituting another agent. The task SHALL keep its status and SHALL gain no assignee, and a later
firing SHALL consider it again.

**This requirement governs staffing, not resumption.** A task that already names an assignee SHALL
continue to be worked by that assignee, whoever it is. It decides who is given work nobody holds,
and never takes work away from an agent already holding it.

**One exception, and only one.** Where a task is in a review status whose assignee is the agent that
produced the work — a row no current edge can create, and which nothing else releases — the Hub
SHALL resolve a replacement reviewer from every available agent in the project. Such a loop names
one agent, and that agent is the author, so restricting the recovery to the named agent would leave
the row wedged permanently. This exception SHALL apply to that recovery alone, and SHALL NOT be read
as permitting substitution for ordinary work.

This restriction SHALL be a filter over the agents the Hub has already determined to be available,
and SHALL NOT introduce any further condition on whether an agent can take a turn. An agent excluded
by it SHALL be excluded because this loop does not name it, never because it was judged unable to
work.

A loop that declares a specification document SHALL be unaffected, and the agents its firings may
staff SHALL remain every available agent in the project. The distinction SHALL be the presence of
the declared document and nothing else.

#### Scenario: A busy agent's loop does not hand its work to a free sibling

- **WHEN** a loop declares no specification document, its job names one agent, that agent is running
  a turn, another agent in the project is free, and the loop's job is fired
- **THEN** no task is started
- **AND** the free agent is not selected
- **AND** the loop's pending task keeps its status and gains no assignee

#### Scenario: A loop does not start a second unassigned task alongside the first

- **WHEN** a loop declares no specification document, two of its tasks have all their dependencies
  met and neither has an assignee, its own agent is free, and another agent in the project is free
- **THEN** exactly one task is started
- **AND** it is started for the agent the loop's job names
- **AND** the second task keeps its status and gains no assignee

#### Scenario: A task that already has an assignee is still worked by that assignee

- **WHEN** a loop declares no specification document, one of its tasks names an assignee other than
  the agent its job names, and the loop's job is fired while its own agent is free
- **THEN** that task is resumed for its existing assignee
- **AND** the assignee is not replaced by the agent the loop's job names

#### Scenario: A wedged review is still recovered from the whole project

- **WHEN** a loop declares no specification document and one of its tasks is in a review status
  whose assignee is the agent that produced the work
- **THEN** a replacement reviewer is resolved from the available agents in the project
- **AND** it is not required to be the agent the loop's job names

#### Scenario: An agent the loop names but cannot be started is not replaced

- **WHEN** a loop declares no specification document and the agent its job names has no runner bound
- **THEN** no other agent is selected in its place

#### Scenario: A loop fires its own agent once that agent is free

- **WHEN** a loop declares no specification document, the agent its job names has finished its turn,
  and the loop's job is fired with claimable work
- **THEN** a task is started for the agent the loop's job names

#### Scenario: A flow still staffs every available agent

- **WHEN** a loop declares a specification document, two of its tasks have all their dependencies
  met, and two eligible agents are available
- **THEN** both tasks are started

## MODIFIED Requirements

### Requirement: A firing is refused while its loop's agent is already running

The Hub SHALL refuse a firing whose loop agent already has a running turn, before that firing claims a task or queues any input, where the loop declares no specification document or where no other agent in the project is free. A loop's agent runs one turn at a time.

**The two arms are not alternatives to one condition.** A loop that declares no document staffs only
the agent its job names, so another agent being free changes nothing about what the firing could do
and cannot lift the refusal. A flow may staff any available agent, so for a flow the refusal stands
only where nobody else is free. This paragraph is what keeps the sentence above true of both.

Where the loop's agent's queue is held by a refusal of the provider's usage allowance, the Hub SHALL
refuse the firing on the same two arms. An agent whose queue is held cannot take a turn until the
hold ends, so a briefing queued for it is as stale by the time it is read as one queued during a
running turn. The hold is the one `agent-conversation-workspace` defines, so this refusal and the
scheduler cannot disagree about whether the agent can take a turn.

Which agent a firing of a **flow** staffs when another agent in the project is free is governed by
`agent-flows`. For a loop that declares no document it is governed by the staffing requirement in
this capability.

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
