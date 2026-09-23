## MODIFIED Requirements

### Requirement: A recurring job may be named as a loop with a purpose and a stop condition

The Hub SHALL let a project opt a scheduled job into being a loop by supplying a purpose, a
wall-clock stop time, a queue-emptiness stop condition, or any combination of the three, at creation
or afterward. A job for which none of these was ever supplied SHALL behave exactly as a plain
scheduled job, with no loop state attached.

Opting a job into being a loop SHALL NOT change its cron, its message, its agent, or its firing
history — a loop's cadence and payload remain exactly what the underlying job already declares.

A loop field supplied for a job that is not becoming a loop SHALL be refused, whether it arrives when
the job is created or when it is updated, and SHALL NOT be silently dropped. The specification
document a loop draws its work from is such a field: a job created naming a document but no purpose
or stop condition would otherwise be accepted as a plain job that ignores the document it was given.

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

#### Scenario: A document named at creation without opting in is refused

- **WHEN** a job is created naming a specification document but supplying none of purpose, a stop
  time, or a queue-emptiness stop condition
- **THEN** the request is rejected with a reason naming what would make the job a loop
- **AND** no job is created

### Requirement: A flow adopts the tasks already materialised from the document it claims

When a loop claims a specification document, it SHALL adopt every task already materialised from
that document which no live loop owns, including every task an archived loop owns that has not
reached a terminal status. Build order SHALL NOT determine whether a flow has a queue.

Today a flow created *after* its document is approved has a permanently empty queue: task creation
stamps the owning loop at materialisation time and nothing back-fills, while every queue query reads
the loop binding rather than the document. The flow is accepted, the claim succeeds, and the queue
is empty forever with no error and no stall reason.

An archived loop owns nothing it could act on. A task it left unfinished is work the document still
asks for, and a loop that later claims the document SHALL take it up, together with whatever its
predecessor's agent is still holding. A task that reached a terminal status under the archived loop
SHALL keep that loop as the record of who ran it.

A task created from a document SHALL be owned by the live loop that claims the document, if there is
one, and SHALL NOT be owned by an archived loop.

#### Scenario: A flow is created after its document is approved
- **WHEN** a document is approved, materialising tasks, and a loop is then created claiming that document
- **THEN** the loop SHALL adopt those tasks
- **AND** the loop's queue SHALL contain them

#### Scenario: A flow is created before its document is approved
- **WHEN** a loop claims a document that is later approved
- **THEN** the tasks SHALL be owned by that loop as they are created
- **AND** the behaviour SHALL be indistinguishable from the case above

#### Scenario: Tasks owned by another loop are not taken
- **WHEN** a loop claims a document whose tasks are already owned by a different live loop
- **THEN** those tasks SHALL NOT be re-assigned

#### Scenario: A successor takes up what an archived loop left unfinished
- **WHEN** a loop that adopted a document's tasks is archived before finishing them
- **AND** a new loop then claims the same document
- **THEN** the new loop SHALL adopt every task the archived loop owned that is not approved or rejected
- **AND** the approved and rejected ones SHALL still name the archived loop

#### Scenario: Tasks created after a loop was archived are not given to it
- **WHEN** a document whose only claiming loop has been archived is approved again, creating tasks
- **THEN** those tasks SHALL NOT be owned by the archived loop
