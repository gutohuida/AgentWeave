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

#### Scenario: An adopted task held by an archived agent says so
- **WHEN** a successor adopts an `in_progress` task whose assignee has since been archived
- **THEN** the task SHALL keep that assignee
- **AND** the successor's firing SHALL NOT brief the archived agent for it
- **AND** the successor SHALL report a stall reason naming the task and the archived assignee

#### Scenario: An adoption is recorded against both loops
- **WHEN** a successor adopts tasks an archived loop owned
- **THEN** one `loop_tasks_adopted` event naming the archived loop, the successor and the moved task ids SHALL be recorded against each of the two loops
- **AND** the events SHALL be written in the same transaction as the move

### Requirement: A loop's queue is the tasks that name it, and each write names its actor

A task MAY be linked to a loop through `loop_id`. The Hub SHALL let a caller of the task list scope
the result to exactly the tasks naming one loop, showing every one of them regardless of status — an
explicit loop scope SHALL hide nothing, matching the guarantee an explicit specification-document
scope already gives.

`loop_id` SHALL be written by exactly three mechanisms, and by no other:

1. **Specification materialisation.** When a specification document is approved and its declared
   tasks are created, any task created for a document that a live loop has declared as its source
   SHALL be written with that loop's id.
2. **Creator authorship.** A caller creating a task MAY supply a `loop_id` directly. The Hub SHALL
   accept it only from the loop's own creator or from the operator, and SHALL reject it from anyone
   else, naming why.
3. **Claim-time adoption.** When a loop claims a specification document, at creation or by an
   update, it SHALL take, in the same transaction as the claim, every task of that document that no
   loop owns and every task of that document that an archived loop owns and that has not reached a
   terminal status. A task a live loop owns SHALL NOT be taken, and a task that reached a terminal
   status under an archived loop SHALL keep that loop's id.

No other code path SHALL set or change a task's `loop_id` once created.

#### Scenario: Scoping the task list to a loop returns exactly its queue

- **WHEN** the task list is requested scoped to one loop
- **THEN** every task naming that loop is returned
- **AND** no task naming a different loop, or no loop, is returned

#### Scenario: A loop-scoped view hides nothing regardless of status

- **WHEN** the task list is scoped to a loop that owns a task in a terminal status
- **THEN** that task is included in the scoped result

#### Scenario: A task created with no loop_id is not in any loop's queue

- **WHEN** a task is created supplying no `loop_id`, and no specification document it might belong
  to declares a loop as its source
- **THEN** the task's `loop_id` is empty
- **AND** the task does not appear in any loop-scoped task list

#### Scenario: Claim-time adoption is the only way a created task changes loop

- **WHEN** a task naming an archived loop has not reached a terminal status, and a new loop claims
  the task's specification document
- **THEN** the task names the new loop
- **AND** no other action, whether archiving, a firing or a transition, changes the task's `loop_id`

### Requirement: A loop MAY declare one specification document as its queue's source

A loop SHALL be creatable with an optional binding to one specification document. Once declared,
this binding SHALL be exactly one document per loop and exactly one live loop per document — a
second loop attempting to declare a document that another live loop has already claimed SHALL be
refused. A loop is live until it is archived: a loop that has ended but has not been archived still
holds its document, and a successor is refused until the ended loop is archived.

When the bound document's declared tasks are created on approval, the Hub SHALL write the live
declaring loop's id onto every task created for that document in that approval. An archived loop
that once declared the document SHALL NOT be written onto any task.

#### Scenario: Approving a loop's source document fills its queue

- **WHEN** a loop declares specification document D as its source, and D is later approved with
  declared tasks
- **THEN** every task D's approval creates carries that loop's id
- **AND** the loop's queue now contains those tasks

#### Scenario: A document already claimed by one live loop cannot be claimed by a second

- **WHEN** a second loop attempts to declare a specification document another live loop has
  already declared as its source
- **THEN** the second loop's creation or update is refused, naming the conflicting loop

#### Scenario: A document whose loop has ended but is not archived is still claimed

- **WHEN** a loop that declared document D has ended but has not been archived, and a second loop
  attempts to declare D
- **THEN** the second loop's creation or update is refused, naming the ended loop
- **AND** once the ended loop is archived, the second loop can claim D

#### Scenario: A document whose declaring loop is archived can be claimed again

- **WHEN** the only loop that declared document D has been archived, and a second loop declares D
- **THEN** the declaration is accepted
- **AND** tasks that D's later approvals create carry the second loop's id, not the archived loop's

#### Scenario: A document with no declaring loop materialises tasks outside every queue

- **WHEN** a specification document with no live loop declaring it as source is approved
- **THEN** the tasks it creates carry no `loop_id`
- **AND** materialisation behaves exactly as it did before this capability existed

### Requirement: A loop and a job are archivable, never deletable

The Hub MUST NOT permanently remove a loop or a scheduled job, nor any record of the runs, queue
history, purpose, or stop state belonging to one. A loop or a job SHALL instead be archivable, which
hides it from default listings and destroys nothing.

Archiving a loop SHALL be an operator action only, and MUST NOT be reachable by an agent.

A successor that claims the same document MAY later adopt an archived loop's unfinished tasks, which
then no longer name the archived loop. The archived loop's queue history SHALL survive that move as
a recorded `loop_tasks_adopted` event naming the archived loop, the successor and the ids of the
tasks moved. The event SHALL be persisted against both loops in the same transaction as the move, so
each loop's own record answers where those tasks went and where they came from.

#### Scenario: Deleting a job is refused

- **WHEN** any caller asks the Hub to delete a job
- **THEN** the request is refused, naming archiving as the available alternative
- **AND** the job, its loop if it has one, and every run record still exist afterwards

#### Scenario: A loop's history survives archiving

- **GIVEN** a loop with a queue history, firings, and a stop reason
- **WHEN** the loop is archived
- **THEN** its purpose, queue history, firings, and stop state are all still retrievable

#### Scenario: A loop's history survives a successor adopting its tasks

- **GIVEN** an archived loop that owned unfinished tasks
- **WHEN** a successor claiming the same document adopts them
- **THEN** the archived loop's own record lists a `loop_tasks_adopted` event naming the successor and
  every moved task id
- **AND** the successor's own record lists the same event naming the archived loop
- **AND** the tasks the archived loop finished still name it

#### Scenario: An agent cannot archive a loop

- **WHEN** an agent asks the Hub to archive a loop
- **THEN** the request is refused, regardless of any standing allowance
