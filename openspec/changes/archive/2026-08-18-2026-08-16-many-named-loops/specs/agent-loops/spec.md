# agent-loops

## ADDED Requirements

### Requirement: A recurring job may be named as a loop with a purpose and a stop condition

The Hub SHALL let a project opt a scheduled job into being a loop by supplying a purpose, a
wall-clock stop time, a queue-emptiness stop condition, or any combination of the three, at creation
or afterward. A job for which none of these was ever supplied SHALL behave exactly as a plain
scheduled job, with no loop state attached.

Opting a job into being a loop SHALL NOT change its cron, its message, its agent, or its firing
history — a loop's cadence and payload remain exactly what the underlying job already declares.

#### Scenario: A job created with no loop fields is not a loop

- **WHEN** a job is created supplying none of purpose, a stop time, or a queue-emptiness stop
  condition
- **THEN** the job has no loop state
- **AND** it fires on its cron exactly as a job created before this capability existed would

#### Scenario: Supplying any one loop field opts a job in

- **WHEN** a job is created or updated supplying at least one of purpose, a stop time, or a
  queue-emptiness stop condition
- **THEN** the job becomes a loop
- **AND** its cron, message, agent, and existing firing history are unchanged

#### Scenario: A loop field cannot be set on a job that is not a loop

- **WHEN** an update supplies a loop field for a job that has never been opted into being a loop
- **THEN** the request is rejected
- **AND** no loop state is created as a side effect of the rejected request

### Requirement: A loop's queue is the tasks that name it

A task MAY be linked to a loop. The Hub SHALL let a caller of the task list scope the result to
exactly the tasks naming one loop, showing every one of them regardless of status — an explicit
loop scope SHALL hide nothing, matching the guarantee an explicit specification-document scope
already gives.

#### Scenario: Scoping the task list to a loop returns exactly its queue

- **WHEN** the task list is requested scoped to one loop
- **THEN** every task naming that loop is returned
- **AND** no task naming a different loop, or no loop, is returned

#### Scenario: A loop-scoped view hides nothing regardless of status

- **WHEN** the task list is scoped to a loop that owns a task in a terminal status
- **THEN** that task is included in the scoped result

### Requirement: A loop's firing is traceable to what it produced

Each firing of a job SHALL record the conversation that firing created or resumed, so that a later
reader can find every output, question, and bound task the firing produced without guessing from
timestamps.

#### Scenario: A firing's conversation is recorded

- **WHEN** a job fires, on schedule or on demand
- **THEN** the firing record identifies the conversation the fire used
- **AND** that conversation's own output and questions are reachable from the firing record without
  a second, separate lookup

### Requirement: A loop surfaces its current state without a caller assembling it by hand

For a job that is a loop, the Hub SHALL surface: its stated purpose; its stop condition and, once
stopped, the reason and time it stopped; a count of its queue's tasks by status; which task, if any,
is its current item; and a count of unanswered, non-declined questions raised across its own firing
history. A job that is not a loop SHALL surface none of this.

#### Scenario: A loop's state is visible on the same surface that already lists jobs

- **WHEN** a loop is read through the job listing or a single job's detail
- **THEN** its purpose, stop condition, queue counts, current item, and open-question count are
  present in that same response
- **AND** a plain job's response carries no loop state

#### Scenario: The current item is the queue's own in-progress task, or its oldest pending one

- **WHEN** a loop's queue holds a task that is in progress or blocked
- **THEN** that task is the loop's current item

- **WHEN** a loop's queue holds no in-progress or blocked task but holds a pending one
- **THEN** its oldest pending task, by creation order, is the loop's current item

- **WHEN** a loop's queue holds no in-progress, blocked, or pending task
- **THEN** the loop has no current item

### Requirement: A loop's stop condition can only ever prevent a firing that was already going to happen

The Hub SHALL check a loop's stop condition immediately before a firing that its own cron or a manual
trigger already caused, and SHALL NOT create, schedule, or trigger any firing that would not
otherwise have occurred. When a stop condition is met, the Hub SHALL skip that firing, record why,
mark the loop stopped with that reason, and stop scheduling further firings for it.

A loop's stop condition SHALL NOT determine what an agent does during a firing, choose the loop's
next queue item, or start a new conversation on the Hub's own initiative.

#### Scenario: A firing past the stop time is skipped, not fired

- **WHEN** a job's cron would fire it after its loop's stop time has passed
- **THEN** that firing is skipped
- **AND** the loop is marked stopped with a reason naming the stop time
- **AND** the job no longer fires on subsequent cron ticks

The queue-emptiness stop condition SHALL mean *drained*, not *never filled*. It SHALL take effect
only once the loop's queue has held at least one task, so that a loop created before its work exists
is not stopped on its first firing.

#### Scenario: A firing with a drained queue is skipped when configured to stop on emptiness

- **WHEN** a job's cron would fire it, its loop has the queue-emptiness stop condition set, the
  loop's queue has held at least one task, and it now holds no task in a non-terminal status
- **THEN** that firing is skipped
- **AND** the loop is marked stopped with a reason naming the empty queue

#### Scenario: A loop whose queue has never held a task is not stopped by the emptiness condition

- **WHEN** a job's cron would fire it, its loop has the queue-emptiness stop condition set, and no
  task has ever named that loop
- **THEN** that firing proceeds
- **AND** the loop is not marked stopped and the job remains enabled

#### Scenario: A loop with no stop condition never stops itself

- **WHEN** a loop has neither a stop time nor the queue-emptiness stop condition set
- **THEN** its firings are never skipped for a stop-condition reason
