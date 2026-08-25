## ADDED Requirements

### Requirement: A flow adopts the tasks already materialised from the document it claims

When a loop claims a specification document, it SHALL adopt every task already materialised from
that document which no other loop owns. Build order SHALL NOT determine whether a flow has a queue.

Today a flow created *after* its document is approved has a permanently empty queue: task creation
stamps the owning loop at materialisation time and nothing back-fills, while every queue query reads
the loop binding rather than the document. The flow is accepted, the claim succeeds, and the queue
is empty forever with no error and no stall reason.

#### Scenario: A flow is created after its document is approved
- **WHEN** a document is approved, materialising tasks, and a loop is then created claiming that document
- **THEN** the loop SHALL adopt those tasks
- **AND** the loop's queue SHALL contain them

#### Scenario: A flow is created before its document is approved
- **WHEN** a loop claims a document that is later approved
- **THEN** the tasks SHALL be owned by that loop as they are created
- **AND** the behaviour SHALL be indistinguishable from the case above

#### Scenario: Tasks owned by another loop are not taken
- **WHEN** a loop claims a document whose tasks are already owned by a different loop
- **THEN** those tasks SHALL NOT be re-assigned

### Requirement: A job SHALL name an agent that exists

Creating or updating a scheduled job SHALL refuse a job naming an agent that is not on the project's
roster, at the moment of the write, and SHALL say that the agent does not exist.

A malformed cron on the same route is already refused at creation. Both facts are checkable at the
same moment, and today only one is checked — so a typo produces a job that is enabled, scheduled,
and fails every five minutes forever, filling the history the operator is meant to read.

#### Scenario: A job names an agent that does not exist
- **WHEN** a job is created naming an agent absent from the roster
- **THEN** the request SHALL be refused
- **AND** the refusal SHALL state that the agent does not exist, not that it has no runner bound

#### Scenario: A job names a real agent
- **WHEN** a job is created naming an agent on the roster
- **THEN** the job SHALL be created

#### Scenario: A job is updated to name a missing agent
- **WHEN** an existing job is updated to name an agent absent from the roster
- **THEN** the update SHALL be refused

#### Scenario: A run fails because the agent has no runner
- **WHEN** a job fires for an agent that exists but has no runner bound
- **THEN** the failure SHALL say the agent has no runner bound, distinct from the agent not existing

### Requirement: A row's status word SHALL be its own status

Where a run record is listed, the status shown SHALL be that record's status, and any other
attribute SHALL be presented as a qualifier rather than in the position a reader takes for the
status.

Measured on a real stall row: the first token read `scheduled`, in the neutral text colour, an inch
from its own amber stall reason. `scheduled` was the record's *trigger*; its status was `skipped`.
A row that reads "scheduled" and "stalled" at once makes the reader work out which word to believe,
and the operator's own test guide told them to look for a skipped row — which is what the surface
did not say.

#### Scenario: A refused firing
- **WHEN** a firing was refused and recorded
- **THEN** the row SHALL lead with its own status
- **AND** the trigger MAY still be shown, qualified so it cannot be read as the status

### Requirement: Two counts of the same thing SHALL agree or be distinguished

Where a summary count and a list describe the same records, the surface SHALL either agree or name
what the count excludes.

Neither number was wrong. A run count that counts firings which actually ran is honestly zero for a
queue that has only ever refused — but shown as `0 runs` directly above a list holding one entry,
the reader meets two counts of one word that disagree. Naming the refusals separately reconciles
them.

#### Scenario: A queue that has only ever refused
- **WHEN** a job has recorded firings that were refused and none that ran
- **THEN** the surface SHALL show the refusals as their own count alongside the run count

#### Scenario: Every firing ran
- **WHEN** no firing was refused
- **THEN** no refusal count SHALL be shown

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

#### Scenario: An agent mid-turn on a task
- **WHEN** the named agent is working the task now
- **THEN** the surface SHALL present the name as the current worker

#### Scenario: An agent the next firing would select
- **WHEN** the named agent is who the next firing would give the task to
- **THEN** the surface SHALL present the name as prospective rather than current

#### Scenario: A task waiting on a person
- **WHEN** the task is blocked and the name is its own assignee
- **THEN** the surface SHALL present the name as assigned rather than as working

#### Scenario: The capacity is not stated
- **WHEN** a surface receives a name with no capacity
- **THEN** it SHALL render the name as it did before this requirement and SHALL NOT infer one
