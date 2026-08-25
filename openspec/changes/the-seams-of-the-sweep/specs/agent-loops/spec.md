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
