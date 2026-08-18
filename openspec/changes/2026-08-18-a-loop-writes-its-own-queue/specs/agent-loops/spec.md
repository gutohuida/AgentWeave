# agent-loops

## MODIFIED Requirements

### Requirement: A loop's queue is the tasks that name it, and each write names its actor

A task MAY be linked to a loop through `loop_id`. The Hub SHALL let a caller of the task list scope
the result to exactly the tasks naming one loop, showing every one of them regardless of status — an
explicit loop scope SHALL hide nothing, matching the guarantee an explicit specification-document
scope already gives.

`loop_id` SHALL be written by exactly two mechanisms, and by no other:

1. **Specification materialisation.** When a specification document is approved and its declared
   tasks are created, any task created for a document that a loop has declared as its source SHALL
   be written with that loop's id.
2. **Creator authorship.** A caller creating a task MAY supply a `loop_id` directly. The Hub SHALL
   accept it only from the loop's own creator or from the operator, and SHALL reject it from anyone
   else, naming why.

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

## ADDED Requirements

### Requirement: A loop MAY declare one specification document as its queue's source

A loop SHALL be creatable with an optional binding to one specification document. Once declared,
this binding SHALL be exactly one document per loop and exactly one loop per document — a second
loop attempting to declare a document another loop has already claimed SHALL be refused.

When the bound document's declared tasks are created on approval, the Hub SHALL write the declaring
loop's id onto every task created for that document in that approval.

#### Scenario: Approving a loop's source document fills its queue

- **WHEN** a loop declares specification document D as its source, and D is later approved with
  declared tasks
- **THEN** every task D's approval creates carries that loop's id
- **AND** the loop's queue now contains those tasks

#### Scenario: A document already claimed by one loop cannot be claimed by a second

- **WHEN** a second loop attempts to declare a specification document another loop has already
  declared as its source
- **THEN** the second loop's creation or update is refused, naming the conflicting loop

#### Scenario: A document with no declaring loop materialises tasks outside every queue

- **WHEN** a specification document with no loop declaring it as source is approved
- **THEN** the tasks it creates carry no `loop_id`
- **AND** materialisation behaves exactly as it did before this capability existed

### Requirement: Only a loop's creator, or the operator, may add to its queue directly

The Hub SHALL accept a caller-supplied `loop_id` when creating a task only from that loop's creator
(the agent that created it, or the operator) or from the operator. A loop also has an executor (the
agent its job triggers on each fire) — the same agent MAY be both creator and executor. Every other
caller, including the loop's own executor when it is not also the creator, SHALL be refused, and the
refusal SHALL name `send_message` to the creator as the path to request the addition instead.

This requirement governs only the *creator-authorship* write path above. It does not apply to tasks
a loop's source document materialises on approval, which name no individual caller as their actor.

#### Scenario: The creator adds a task to its own loop

- **WHEN** an agent that created loop L creates a task supplying L's id
- **THEN** the task is created with `loop_id` set to L

#### Scenario: The operator adds a task to any loop

- **WHEN** the operator creates a task supplying any loop's id
- **THEN** the task is created with that loop's `loop_id` set

#### Scenario: An executor that is not the creator cannot add to the queue

- **WHEN** an agent that is loop L's executor but not its creator attempts to create a task
  supplying L's id
- **THEN** the request is refused
- **AND** the refusal names `send_message` to L's creator as the alternative

### Requirement: A firing claims its queue's current item before the turn begins

Each time a loop's job fires, the Hub SHALL select the queue's current item deterministically — the
queue's existing task in an active, non-terminal status if one exists, else its oldest task in an
entry status — and SHALL mark it as claimed by that firing before the firing's agent begins its turn.
No firing SHALL leave the choice of which queued task to work to the firing agent's own judgement.

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

### Requirement: A loop's continuity across firings is by checkpoint, not by resumed session

Each firing of a loop's job SHALL be briefed with the most recent checkpoint recorded by any prior
firing of that same loop, regardless of which conversation produced it. A job that carries a loop
SHALL refuse a `session_mode` of `resume`, naming loop continuity as the reason, rather than
silently ignoring the setting.

#### Scenario: A second firing is briefed with the first firing's checkpoint

- **WHEN** a loop's job fires a second time, and its first firing's conversation produced a
  checkpoint before ending
- **THEN** the second firing's briefing includes that checkpoint's content
- **AND** this holds even though the second firing's conversation is a different conversation than
  the first's

#### Scenario: A loop's first firing has no checkpoint to inherit

- **WHEN** a loop's job fires for the first time
- **THEN** the firing's briefing carries no prior checkpoint content
- **AND** the fire is not refused or delayed for lacking one

#### Scenario: Setting resume mode on a loop's job is refused

- **WHEN** an update sets `session_mode` to `resume` on a job that carries a `Loop`
- **THEN** the update is refused, naming that the job's continuity is by checkpoint

### Requirement: A firing's briefing is bounded

The content composed ahead of a loop's job message for each firing SHALL include the loop's purpose,
the item claimed for that firing, and the prior checkpoint content when one exists. The prior
checkpoint content included SHALL be bounded to a fixed size, so that a long-running loop's
accumulated history cannot grow the size of what a single firing is asked to read.

#### Scenario: A well-formed prior checkpoint fits in full

- **WHEN** a firing's inherited checkpoint content is within the fixed size bound
- **THEN** the briefing includes it in full

#### Scenario: An oversized prior checkpoint is truncated, not omitted

- **WHEN** a firing's inherited checkpoint content exceeds the fixed size bound
- **THEN** the briefing includes a truncated version up to that bound
- **AND** the briefing is not silently sent with no prior context at all

### Requirement: An empty queue with a request still in flight terminates, and is recorded

When a loop's stop condition fires because its queue is empty, the Hub SHALL check whether an
unanswered request for more work — a message to the loop's creator, or an unanswered question — was
outstanding at that moment, and SHALL record what it found as part of stopping the loop. The loop
SHALL still stop; an outstanding request SHALL NOT create a third, waiting state.

#### Scenario: The queue empties with no outstanding request

- **WHEN** a loop's queue empties and no message to its creator or unanswered question is
  outstanding
- **THEN** the loop stops
- **AND** the stop is recorded with no pending request noted

#### Scenario: The queue empties while a request for more work is outstanding

- **WHEN** a loop's queue empties while its executor has an unread message to the creator or an
  unanswered question outstanding
- **THEN** the loop still stops
- **AND** the stop is recorded noting the outstanding request, so it can be reviewed later

### Requirement: A self-created loop's queue accepts additions from its creator only until its first fire

The Hub SHALL end a self-created loop's creator privilege to add tasks directly once that loop has
fired for the first time, where "self-created" means the loop's creator and executor are the same
agent. After a self-created loop's first fire, the creator agent MAY request an addition only by
asking the operator and receiving an answer; a direct addition attempt SHALL be refused. This
requirement does not narrow the creator privilege for a loop whose creator and executor are
different agents.

#### Scenario: A self-created loop accepts creator additions before its first fire

- **WHEN** an agent creates a loop for itself and adds a task to it before the loop has fired
- **THEN** the addition is accepted

#### Scenario: A self-created loop refuses a direct creator addition after its first fire

- **WHEN** an agent that created a loop for itself attempts to add a task directly after that loop
  has already fired once
- **THEN** the addition is refused, naming that operator approval is required

#### Scenario: A self-created loop accepts an addition the operator approved

- **WHEN** an agent that created a loop for itself asks the operator for an addition after the
  loop's first fire, and the operator approves it
- **THEN** the task is added with that loop's id

### Requirement: A loop has a controller, defaulting to the operator, which may be delegated

The Hub SHALL record for each loop a controller, which decides whether that loop's queue may be
extended, and which SHALL default to the operator.

The operator SHALL be able to delegate control to the loop's creator agent, and to take it back,
after the loop has been created. Where the operator holds control, a request to extend the queue
SHALL be relayed to the operator and SHALL change nothing until the operator decides. Where control
has been delegated, the creator agent SHALL be able to decide the request itself. Each change of
control SHALL be recorded against the loop with the actor responsible and the time it occurred.

#### Scenario: A loop's control defaults to the operator

- **WHEN** a loop is created
- **THEN** its controller is the operator
- **AND** an extension of its queue changes nothing until the operator decides

#### Scenario: Control is delegated after creation

- **WHEN** the operator delegates control of an existing loop to its creator agent
- **THEN** subsequent extension requests are decided by that agent
- **AND** the change of control is recorded against the loop with its actor and time

#### Scenario: Control is taken back

- **WHEN** the operator takes back control of a loop it had delegated
- **THEN** subsequent extension requests are presented to the operator again

### Requirement: An edit to a loop takes effect at its next firing and never during one

The Hub SHALL accept an edit to a loop at any time, including while one of its firings is running,
and SHALL apply that edit at the loop's next firing.

A firing already running SHALL continue under the definition it was briefed with. The Hub SHALL
report an edit that is pending separately from the definition currently in force, so that an operator
can tell what is staged from what is live. Each edit SHALL be recorded against the loop with the
actor responsible and the time it occurred.

#### Scenario: An edit during a firing does not disturb that firing

- **GIVEN** a loop with a firing in progress
- **WHEN** its purpose or stop condition is edited
- **THEN** the edit is accepted
- **AND** the running firing continues under the definition it was briefed with

#### Scenario: The next firing sees the edit

- **WHEN** the loop fires after an edit was accepted
- **THEN** that firing is briefed with the edited definition
- **AND** the edit is no longer reported as pending

#### Scenario: A pending edit is distinguishable from the definition in force

- **GIVEN** a loop with an accepted edit that has not yet been applied
- **WHEN** the loop is inspected
- **THEN** the pending edit is reported as pending
- **AND** the definition currently in force is reported separately

### Requirement: A task offered to a stopped loop is refused and offered to a successor

The Hub SHALL refuse a task added to a loop that has stopped, stating the reason that loop stopped
and when it stopped. Refusing SHALL NOT restart a stopped loop.

The refused task SHALL be offered as the initial work of a new loop, so that a task written moments
after its intended loop terminated is not discarded.

#### Scenario: A late task is refused with the reason the loop stopped

- **GIVEN** a loop that stopped because its queue emptied
- **WHEN** a task is added to it
- **THEN** the addition is refused
- **AND** the refusal states that the loop stopped because its queue emptied, and when

#### Scenario: The refused task is offered to a new loop

- **WHEN** a task is refused because its loop has stopped
- **THEN** it is offered as the initial work of a new loop
- **AND** the stopped loop remains stopped

### Requirement: A loop's history is answerable for that loop alone

The Hub SHALL record against the loop each event in its life: its creation, each edit, each change of
control, each addition to its queue, each firing, and its stop with the reason. Each SHALL carry the
actor responsible and the time it occurred.

The Hub SHALL let a caller retrieve that history scoped to one loop, without filtering a
project-wide record by hand.

#### Scenario: A loop's history is retrievable on its own

- **WHEN** a caller requests one loop's history
- **THEN** the events of that loop's life are returned in order
- **AND** no event belonging to a different loop is returned

#### Scenario: Every recorded event names its actor

- **WHEN** a loop's history is retrieved
- **THEN** each event states the actor responsible and the time it occurred

### Requirement: A firing in progress is distinguishable from one that has finished

The Hub SHALL record a loop firing as in progress for as long as its run is executing, and SHALL
distinguish that state from a firing that completed and from one that failed.

#### Scenario: A running firing reports as running

- **GIVEN** a loop firing whose run is executing
- **WHEN** the loop is inspected
- **THEN** the firing is reported as in progress

#### Scenario: A finished firing is not reported as running

- **WHEN** a firing's run has ended
- **THEN** the firing is no longer reported as in progress
- **AND** whether it completed or failed is reported

### Requirement: A loop and a job are archivable, never deletable

The Hub MUST NOT permanently remove a loop or a scheduled job, nor any record of the runs, queue
history, purpose, or stop state belonging to one. A loop or a job SHALL instead be archivable, which
hides it from default listings and destroys nothing.

Archiving a loop SHALL be an operator action only, and MUST NOT be reachable by an agent.

#### Scenario: Deleting a job is refused

- **WHEN** any caller asks the Hub to delete a job
- **THEN** the request is refused, naming archiving as the available alternative
- **AND** the job, its loop if it has one, and every run record still exist afterwards

#### Scenario: A loop's history survives archiving

- **GIVEN** a loop with a queue history, firings, and a stop reason
- **WHEN** the loop is archived
- **THEN** its purpose, queue history, firings, and stop state are all still retrievable

#### Scenario: An agent cannot archive a loop

- **WHEN** an agent asks the Hub to archive a loop
- **THEN** the request is refused, regardless of any standing allowance

### Requirement: A loop that is still running cannot be archived

The Hub SHALL refuse to archive a loop that has neither completed nor stopped, so that archiving can
never conceal work that is still firing.

#### Scenario: Archiving a running loop is refused

- **GIVEN** a loop that is still enabled and firing
- **WHEN** the operator attempts to archive it
- **THEN** the request is refused, stating that it must be stopped or complete first

#### Scenario: A stopped loop can be archived

- **GIVEN** a loop that has stopped or completed
- **WHEN** the operator archives it
- **THEN** the loop is archived and no longer appears in default listings

### Requirement: How a loop ended is a distinct value, not only a written reason

A loop that ends SHALL record how it ended as a distinct value that can be filtered and counted,
separately from the human-readable reason it already records. Completing — ending because its queue
drained — SHALL be distinguishable from stopping for any other cause without interpreting prose.

#### Scenario: A drained queue records completion as a value

- **WHEN** a loop ends because every task naming it has reached a terminal status
- **THEN** the loop records that it completed, as a value distinct from its written reason

#### Scenario: Stopping early is distinguishable from completing

- **GIVEN** one loop that ended because its queue drained and another stopped by the operator
- **WHEN** the project's loops are listed and counted by how they ended
- **THEN** the two are counted separately, without matching on the text of any reason

### Requirement: A claimed task is still the loop's current item

A task claimed by a firing SHALL be reported as the loop's current item even before any later step
moves it to an in-progress status. The Hub MUST NOT omit the claimed task from a loop's summary
solely because of the status a claim assigns it.

#### Scenario: A freshly claimed task is reported

- **GIVEN** a firing that has claimed its queue's item and not yet begun its turn
- **WHEN** the loop's summary is retrieved
- **THEN** the claimed task is reported as the loop's current item

### Requirement: A project's loops are listable and individually inspectable

The Hub SHALL let the operator list every loop in a project, whatever its state, and inspect any one
of them individually. A loop's listing entry SHALL carry a label the operator can recognise it by,
without the caller having to fetch its job separately.

Listing SHALL be scoped to the project and MUST NOT require naming a conversation, since a loop's
firings each occupy a conversation of their own and none of them is the loop.

#### Scenario: Every loop in a project is listable

- **WHEN** the operator lists a project's loops
- **THEN** every loop is returned regardless of whether it is running, complete, stopped, or archived
- **AND** each carries a label, its purpose, how it ended if it has, and its queue counts

#### Scenario: A loop is inspectable without naming a conversation

- **WHEN** the operator inspects one loop
- **THEN** its queue, current item, firing history, and whether a firing is in progress are returned
- **AND** no conversation identifier is required to make the request

#### Scenario: Archived loops are excluded from the default listing

- **GIVEN** a project with archived and unarchived loops
- **WHEN** the operator lists the project's loops without asking for archived ones
- **THEN** only the unarchived loops are returned
