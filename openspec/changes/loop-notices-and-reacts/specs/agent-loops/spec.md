## MODIFIED Requirements

### Requirement: A firing claims its queue's current item before the turn begins

Each time a loop's job fires **and proceeds to claim**, the Hub SHALL select the queue's current item
deterministically — the queue's existing task in an active, non-terminal status if one exists, else
its oldest task in an entry status — and SHALL mark it as claimed by that firing before the firing's
agent begins its turn. No firing SHALL leave the choice of which queued task to work to the firing
agent's own judgement.

A firing SHALL NOT reach the claim at all when it is refused beforehand, whether by the loop's stop
condition, by its agent already running, or by its queue being stalled. A refused firing SHALL claim
nothing, SHALL queue no input for its agent, and SHALL leave every task's status and assignee
unchanged.

#### Scenario: A firing claims the oldest open item when nothing is already in progress

- **WHEN** a loop's job fires and its queue holds only tasks in an entry status
- **THEN** the firing claims the oldest one by creation time
- **AND** that task is marked as claimed before the agent's turn begins

#### Scenario: A firing resumes an item a prior firing left unfinished

- **WHEN** a loop's job fires and its queue already holds a task in an active, non-terminal status
- **THEN** the firing claims that task rather than starting a different one

#### Scenario: A firing with an empty queue claims nothing

- **WHEN** a loop's job fires and its queue holds no task in an entry or active status
- **THEN** the firing claims no item
- **AND** whether the fire proceeds at all is governed by the loop's stop condition, unchanged by
  this requirement

#### Scenario: A refused firing leaves the queue untouched

- **WHEN** a firing is refused before the claim
- **THEN** no task changes status or assignee
- **AND** no input is queued for the loop's agent

## ADDED Requirements

### Requirement: A firing is refused while its loop's agent is already running

The Hub SHALL refuse a firing whose loop agent already has a running turn, before that firing claims
a task or queues any input. A loop's agent runs one turn at a time.

The loop's job SHALL remain enabled and remain scheduled, so that a later firing proceeds once the
agent is free.

#### Scenario: A firing during a live turn queues nothing

- **WHEN** a loop's agent has a running turn and the loop's job fires
- **THEN** the firing is refused
- **AND** no inbound queue entry is created for that agent

#### Scenario: Repeated firings during one turn do not accumulate work

- **WHEN** a loop's job fires several times while its agent's single turn is running
- **THEN** the number of inbound queue entries created by those firings is zero

#### Scenario: The loop proceeds once the agent is free

- **WHEN** a loop's agent finishes its turn and the loop's job fires again with claimable work
- **THEN** the firing proceeds and claims a task

### Requirement: A firing is refused while its queue is stalled

The Hub SHALL refuse a firing whose queue is stalled, before queueing any input, and SHALL record a
reason naming what the queue is waiting on. A queue is stalled when it holds tasks that are not
terminal and none of them is claimable.

Where nothing is claimable and no dependency gate is involved, that reason SHALL name how many tasks
are open and in which statuses. Where instead a dependency gate refuses every candidate, the reason
is governed by "A queue gated on unapproved work is stalled, never stopped", which requires it to
distinguish an unmet prerequisite from a rejected one. That reason names counts and causes rather
than statuses, and this requirement SHALL NOT be read to demand both of it: the operator's remedy
there is the prerequisite, not the queue's own status breakdown.

The loop's job SHALL remain enabled and remain scheduled. A stalled queue is not a finished one, and
the operator resolving the stall SHALL be sufficient for a later firing to proceed with no further
action.

#### Scenario: A stalled queue refuses the firing and states why

- **WHEN** a loop's job fires and every non-terminal task in its queue is unclaimable, with no
  dependency gate involved
- **THEN** the firing is refused
- **AND** the recorded reason names the count and statuses of the open tasks

#### Scenario: A gated stall states its gate rather than its statuses

- **WHEN** a loop's job fires and every candidate in its queue is refused by the dependency gate
- **THEN** the firing is refused
- **AND** the recorded reason names the gating rather than the queue's status breakdown

#### Scenario: A stalled loop is not disabled

- **WHEN** a loop's job fires with a stalled queue
- **THEN** the job remains enabled and the loop records no stop reason

#### Scenario: A resolved stall resumes on the next firing

- **WHEN** a stalled loop's queue gains a claimable task and the job fires again
- **THEN** the firing claims that task

### Requirement: A firing that does not fire records only what is new

The Hub SHALL record a loop's execution history such that repeated identical refusals do not each
produce a new entry. A loop that ticks without working MUST NOT bury the record of the firings that
did work.

- A firing refused because the agent is already running SHALL create no execution record. The running
  record already states that the agent is working.
- A firing refused because the queue is stalled SHALL create one execution record for that stall,
  and each subsequent refusal for the same stall SHALL increment a count on that record rather than
  creating another.
- A firing refused because the loop stopped SHALL create an execution record, as it does today.

#### Scenario: A busy refusal writes no history entry

- **WHEN** a loop's job is fired several times while its agent is running
- **THEN** the loop's execution history gains no entries from those firings

#### Scenario: A continuing stall increments rather than appends

- **WHEN** a loop's job fires repeatedly against the same stalled queue
- **THEN** the loop's execution history holds exactly one entry for that stall
- **AND** that entry's tick count equals the number of refused firings

#### Scenario: Real firings stay visible under a fast tick rate

- **WHEN** a loop alternates between firings that claim work and long periods of refusal
- **THEN** the most recent execution records still include the firings that claimed work
