## MODIFIED Requirements

### Requirement: A loop surfaces its current state without a caller assembling it by hand

For a job that is a loop, the Hub SHALL surface: its stated purpose; its stop condition and, once stopped, the reason and time it stopped; a count of its queue's tasks by status; which task, if any, is its current item; and a count of questions raised across its own firing history that are unanswered, non-declined, and still being waited on. A job that is not a loop SHALL surface none of this.

The last clause is new and it narrows the count. A question whose bounded wait ended without an
answer is unanswered and undeclined and always will be, because nothing ever answers it — but nobody
is waiting on it, the agent proceeded, and the operator reading this number reads it as work that
still needs them. A count that only ever grows is a count they stop reading.

#### Scenario: A loop's state is visible on the same surface that already lists jobs

- **WHEN** a loop is read through the job listing or a single job's detail
- **THEN** its purpose, stop condition, queue counts, current item, and open-question count are
  present in that same response
- **AND** a plain job's response carries no loop state

#### Scenario: A question whose wait ended is not counted as open

- **GIVEN** a loop whose firing asked a blocking question that went unanswered until its wait ended
- **WHEN** the loop's state is read
- **THEN** that question is not part of its open-question count

### Requirement: An agent attributed to a task SHALL be attributed in a stated capacity

Where a surface names the agent associated with a task, it SHALL state what that association means,
and that meaning SHALL NOT vary silently with the task's status.

The value was right and the presentation was wrong. For a task in progress the name is the agent
mid-turn; for a completed one awaiting review it is whichever agent the next firing would hand the
review to. Rendered identically, `completed | relay` reads as "relay is working this" and means
"relay is who would review this". A column whose meaning changes row to row is unreadable exactly
when a flow puts several such rows on one card.

The capacity SHALL be determined where it is known. By the time a surface receives the name, work
in flight and a firing's prospective selections are indistinguishable; only the computation that
merges them can still tell them apart.

**The capacity SHALL be determined in exactly one place**, and the values it is derived from SHALL
NOT be reachable by the surfaces that render it. A collection computed for one purpose and left
publicly readable will be read for another: a collection meaning "this firing cannot staff anybody
onto this task" was rendered as "this agent is mid-turn on it", and told the operator an agent was
working a task whose run had already failed. Naming such a collection more carefully is not
sufficient, because the next reader is not bound by the name; it SHALL NOT be reachable at all.

**Each capacity SHALL be derived from the source that answers it**, and no source SHALL be asked a
question it does not answer. Whether an agent is mid-turn on a task is answered by the runs the
system started, never by what a firing could or could not staff, **and never by the task's own
status**. What a firing would do next is answered by that firing's own selection. Who a task is
assigned to is answered by the task.

That last clause decides a case which used to be impossible. A task waiting on a person can now have
a run of its own in flight, because a task is recorded as waiting from the moment its question is
asked rather than when its run ends. The waiting status is therefore no longer evidence that nothing
is running, and the runs SHALL be consulted for every attribution rather than only for the ones a
firing could not staff. What the task is waiting for is carried by its status and its stated reason,
which is where a reader already looks for it; borrowing the capacity column to say it a second time
would cost the column its own meaning.

The capacities SHALL be distinguishable and SHALL number four: an agent mid-turn on the task; an
agent holding it that nothing is running and no firing can staff; an agent a firing would select
next; and a task's own assignee where no selection is being made. **An agent holding work that
nothing is running SHALL NOT be presented as working it**, and SHALL be presented in a way that
reserves the unqualified name for work actually in progress.

The capacity SHALL NOT be named a role. In this system a role already denotes a charter, which an
agent may legitimately not have, and separately denotes whether a turn is work or review; a third
sense on the same word makes each unreadable.

#### Scenario: An agent mid-turn on a task
- **WHEN** the named agent is working the task now
- **THEN** the surface SHALL present the name as the current worker

#### Scenario: An agent the next firing would select
- **WHEN** the named agent is who the next firing would give the task to
- **THEN** the surface SHALL present the name as prospective rather than current

#### Scenario: A task waiting on a person with nothing running
- **WHEN** the task is blocked, no run of it is in progress, and the name is its own assignee
- **THEN** the surface SHALL present the name as assigned rather than as working

#### Scenario: A task waiting on a person whose run is still in flight
- **WHEN** the task is blocked and a run bound to it is in progress
- **THEN** the surface SHALL present the name as the current worker
- **AND** what the task is waiting for is stated by the task rather than by the capacity

#### Scenario: The capacity is not stated
- **WHEN** a surface receives a name with no capacity
- **THEN** it SHALL render the name as it did before this requirement and SHALL NOT infer one

#### Scenario: An agent holding work that nothing is running
- **WHEN** a task is held by an agent, no run of that work is in progress, and no firing can staff it
- **THEN** the surface SHALL present the name as held rather than as working
- **AND** the presentation SHALL be distinguishable from an agent mid-turn on the task

#### Scenario: A review whose run has ended is not presented as working
- **WHEN** a task is under review, its review run has ended, and no run is in progress for it
- **THEN** the surface SHALL NOT present its reviewer as working the task

#### Scenario: The capacity has a single determination
- **WHEN** more than one surface presents the capacity of an agent on a task
- **THEN** every one of them obtains it from the same determination
- **AND** none of them computes it from the values that determination is derived from

#### Scenario: The determination's inputs are unreachable
- **WHEN** any module other than the one that determines capacity is examined
- **THEN** it does not read the firing decision's collection of work a firing cannot staff
