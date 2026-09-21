## ADDED Requirements

### Requirement: A firing staffs a loop that declares no document only with the agent its job names

The Hub SHALL staff a task that has no assignee, in a loop that declares no specification document, only with the agent that loop's job names, and SHALL NOT select any other agent for it.

Where that agent cannot take a turn, the firing SHALL staff nobody for that task rather than
substituting another agent. The task SHALL keep its status and SHALL gain no assignee, and a later
firing SHALL consider it again.

**This requirement governs staffing, not resumption.** A task that already names an assignee SHALL
NOT have that assignee replaced by this requirement, whoever it is. It decides who is given work
nobody holds, and never takes work away from an agent already holding it. It does not promise that
such a task is resumed on any particular firing: the busy guard refuses the whole firing while the
loop's own agent is running or held, so a task assigned to a sibling waits with the rest of the
queue until that agent is free.

**One exception, and only one: reviewer recovery.** Where a task is in a review status held by an
assignee that cannot complete the review — the agent that produced the work, or a reviewer whose
turn ended without recording a verdict — this requirement SHALL NOT narrow the pool from which a
replacement reviewer is resolved to the agent the loop's job names. Such a loop names one agent, and
on the first of those rows that agent **is** the author, whom the resolver excludes by construction,
so narrowing the recovery would leave the row wedged permanently.

**This exception is a non-restriction, not a guarantee.** It states only that this requirement adds
no narrowing of its own. Whether a replacement reviewer is found at all is governed by *A loop does
not staff a review of its own agent's work* in this capability — which already requires that such a
row "SHALL still be recovered by reassignment without moving status" — and by the reviewer ladder's
own requirements, several of which end a recovery with nobody staffed and the operator told why.
This exception SHALL apply to reviewer recovery alone, and SHALL NOT be read as permitting
substitution for ordinary work.

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

#### Scenario: A wedged review's recovery is not narrowed to the loop's own agent

- **WHEN** a loop declares no specification document and one of its tasks is in a review status
  whose assignee is the agent that produced the work
- **THEN** the pool the replacement reviewer is resolved from is not narrowed to the agent the
  loop's job names
- **AND** where that recovery ends with nobody staffed, it is for a reason this requirement did not
  create

#### Scenario: A verdict-less review's substitution is not narrowed either

- **WHEN** a loop declares no specification document and one of its tasks is in a review status
  whose assignee is a reviewer whose turn ended without recording a verdict
- **THEN** the pool the substitute reviewer is resolved from is not narrowed to the agent the loop's
  job names

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

The loop's job SHALL remain enabled and remain scheduled, so that a later firing proceeds once the
agent is free.

#### Scenario: A firing during a live turn queues nothing

- **WHEN** a loop's agent has a running turn, no other agent in the project is free, and the loop's job fires
- **THEN** the firing is refused
- **AND** no inbound queue entry is created for that agent

#### Scenario: Repeated firings during one turn do not accumulate work

- **WHEN** a loop's job fires several times while its agent's single turn is running and no other agent in the project is free
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
**either the loop declares no specification document, or no other agent in the project is free, or
the loop's queue holds no task in a non-terminal status.** It records nothing, deliberately, so
there is no firing record to read a reason from, and the most recent record is some earlier
firing's.

Where the loop's queue holds no task in a non-terminal status, the answer SHALL say so, and SHALL
NOT state that no other agent is free. Stating that no other agent is free when one is free tells
the operator to free an agent, which would change nothing; what the loop lacks is work. Where the
loop declares a specification document and its queue holds an open task, the guard refused because
no other agent is free, and the answer SHALL say so.

This requirement does not state what the answer says, beyond the reason the guard gave, for a loop
that declares no specification document and whose queue holds an open task. That loop is refused
whether or not another agent is free, so the roster is not its reason; which sentence names that
reason is not yet decided.

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
