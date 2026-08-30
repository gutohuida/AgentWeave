# agent-loops Specification

## Purpose
TBD - created by archiving change 2026-08-16-many-named-loops. Update Purpose after archive.
## Requirements
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

Each time a loop's job fires and proceeds to claim, the Hub SHALL select the queue's current item or
items deterministically — the queue's existing tasks in an active, non-terminal status if any exist,
else its oldest tasks in an entry status — and SHALL mark each as claimed by that firing before the
firing's agent begins its turn. No firing SHALL leave the choice of which queued task to work to the
firing agent's own judgement.

Where the loop is a flow, the Hub SHALL also determine which agent works each selected task, by the
same standard: deterministically, and never by asking an agent.

A firing SHALL NOT reach the claim at all when it is refused beforehand, whether by the loop's stop
condition, by its agent already running, or by its queue being stalled. A refused firing SHALL claim
nothing, SHALL queue no input for any agent, and SHALL leave every task's status and assignee
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
- **AND** no input is queued for any agent

#### Scenario: A flow's firing determines the agent alongside the task

- **WHEN** a flow's firing selects a task
- **THEN** it also determines which agent is fired for it, without asking any agent
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

Reporting the two separately is not sufficient on its own. Where a loop is presented to the operator,
a pending edit SHALL be shown, each value SHALL state in words when it applies, and a loop with no
pending edit SHALL show nothing — the absence of an indicator is itself the statement that the
definition on screen is the one in force. A field the edit did not touch MUST NOT be presented as
changing.

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

#### Scenario: The operator is shown which definition is in force

- **GIVEN** a loop with an accepted edit that has not yet been applied
- **WHEN** the operator opens that loop
- **THEN** each staged value is shown beside the value it will replace
- **AND** each of the two states in words when it applies, rather than by position or colour alone
- **AND** a field the edit did not touch is not shown as changing

#### Scenario: A running firing is said to keep the live definition

- **GIVEN** a loop with a pending edit and a firing already in progress
- **WHEN** the operator opens that loop
- **THEN** it states that the running firing keeps the definition currently in force
- **AND** that the edit reaches the firing after it

#### Scenario: A loop with no pending edit shows no indicator

- **GIVEN** a loop with no staged edit
- **WHEN** the operator opens it
- **THEN** no pending-edit indicator is shown
- **AND** the definition shown is the one in force, unqualified

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

Archiving a loop's job SHALL retire the loop with it. A loop has exactly one job, and an archived job
never fires — so a loop whose job is archived is not firing and SHALL NOT be treated as though it
were. Retiring it in that one operation is what satisfies the rule above, not an exception to it.

Measured 2026-08-21: archiving a job left its loop active and listed, and archiving that loop was
then refused as *"still running"* although nothing could fire it. Clearing it took setting a stop
time in the past, firing once so the stop condition was evaluated, and only then archiving — three
steps, none of them discoverable from the refusal.

#### Scenario: Archiving a running loop is refused

- **GIVEN** a loop that is still enabled and firing
- **WHEN** the operator attempts to archive it
- **THEN** the request is refused, stating that it must be stopped or complete first

#### Scenario: A stopped loop can be archived

- **GIVEN** a loop that has stopped or completed
- **WHEN** the operator archives it
- **THEN** the loop is archived and no longer appears in default listings

#### Scenario: Archiving a job retires its loop

- **GIVEN** an enabled loop whose job has not been archived
- **WHEN** the operator archives that job
- **THEN** the loop is retired in the same operation
- **AND** it no longer appears in default loop listings
- **AND** the operator is not required to stop it first

#### Scenario: A loop retired with its job keeps everything

- **GIVEN** a loop with a queue history, firings, and a purpose
- **WHEN** its job is archived
- **THEN** its purpose, queue history, firings, and stop state are all still retrievable

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

A task claimed by a firing SHALL be reported among the loop's current items even before any later
step moves it to an in-progress status. The Hub MUST NOT omit a claimed task from a loop's summary
solely because of the status a claim assigns it.

A firing MAY claim more than one task, so a loop's current items are a set rather than a single
value. Where one is claimed the set holds one; a caller SHALL NOT have to distinguish the two cases.

Each reported current item SHALL name the agent fired for it, since under a flow the agent differs
between items in the same firing.

#### Scenario: A freshly claimed task is reported

- **GIVEN** a firing that has claimed its queue's item and not yet begun its turn
- **WHEN** the loop's summary is retrieved
- **THEN** the claimed task is reported among the loop's current items

#### Scenario: Several tasks claimed by one firing are all reported

- **GIVEN** a firing that has claimed two tasks
- **WHEN** the loop's summary is retrieved
- **THEN** both are reported, each naming the agent fired for it

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

### Requirement: A conversation a loop firing created names the loop that created it

A conversation created by a loop firing SHALL name the loop that created it, wherever conversations
are listed, by the same label the loop is listed under elsewhere. A loop firing starts a conversation
of its own, so without this an agent's conversations accumulate threads the operator never began and
cannot tell apart from the ones they did.

The naming SHALL distinguish a loop firing from a plain scheduled job. A conversation created by a
job that has no loop SHALL carry no loop and be marked as none, since both are created the same way
and are otherwise indistinguishable.

Naming a loop SHALL lead to that loop's existing record rather than to a second place its history is
kept.

#### Scenario: A firing's conversation names its loop

- **GIVEN** a loop that has fired
- **WHEN** the operator lists the conversations of the agent that ran it
- **THEN** the conversation the firing created names that loop
- **AND** the name shown is the one the loop is listed under elsewhere

#### Scenario: A plain scheduled job's conversation names no loop

- **GIVEN** a scheduled job with no loop, which has fired
- **WHEN** the operator lists the conversations of the agent that ran it
- **THEN** that conversation carries no loop
- **AND** it is not marked as belonging to one

#### Scenario: An operator-started conversation names no loop

- **WHEN** the operator lists conversations they started themselves
- **THEN** none of them names a loop

#### Scenario: Naming a loop leads to that loop's record

- **GIVEN** a conversation that names a loop
- **WHEN** the operator follows that name
- **THEN** the loop's existing record opens
- **AND** no second copy of its firing history is presented

### Requirement: A time shown for a loop is the instant it happened

A time SHALL be shown to the operator as the instant it happened, independently of where the
operator's machine is. Every time the Hub records is an instant in UTC — when an edit was staged,
when a firing happened, when a loop stopped — and where the operator reads one, it is that instant
they must be reading.

A time the Hub reports without stating its zone SHALL be read as UTC, since that is what it is. A
time that does state its zone SHALL be read as stated and MUST NOT be overridden.

#### Scenario: A time is read as the instant it happened, not as local time

- **GIVEN** an operator whose machine is not on UTC
- **WHEN** they open a loop moments after staging an edit
- **THEN** the edit is shown as having been staged moments ago

#### Scenario: A time that states its zone is respected

- **GIVEN** a time reported with an explicit zone
- **WHEN** it is shown to the operator
- **THEN** it is presented as the instant that zone makes it, not shifted again

### Requirement: Consecutive firings of one loop occupy one row

A run of consecutive conversations created by the same loop **and belonging to the same agent** SHALL
be presentable, where conversations are listed, as a single row expandable to the firings it stands
for. A loop left running fills the list with threads the operator never began; naming each one is not
sufficient once there are enough of them.

A change of agent SHALL break the run. Consecutive firings by different agents are different events —
under a flow, an implementer followed by a reviewer is the ordinary case, and collapsing them
together would hide the handover that is the most informative thing on the list.

Collapsing SHALL NOT reorder the list. Only *consecutive* conversations may be collapsed together,
so that a conversation which fell between two firings keeps its place between them.

Collapsing SHALL NOT hide that a firing needs the operator: a run containing a conversation waiting
for them SHALL say so without being expanded. A run containing the conversation currently open SHALL
present it.

#### Scenario: A run of firings is one row

- **GIVEN** several consecutive conversations created by the same loop and the same agent
- **WHEN** the operator lists them
- **THEN** they occupy a single row naming the loop and stating how many there are
- **AND** expanding it presents each firing

#### Scenario: A change of agent breaks the run

- **GIVEN** consecutive conversations created by one flow, the first two by one agent and the third
  by another
- **WHEN** the operator lists them
- **THEN** the third does not collapse into the row holding the first two

#### Scenario: A conversation between two runs keeps its place

- **GIVEN** a loop's firings, then a conversation the operator started, then more of that loop's
  firings
- **WHEN** the operator lists them
- **THEN** the conversation they started still falls between the two runs
- **AND** the runs are not joined across it
#### Scenario: A waiting firing is visible without expanding

- **GIVEN** a collapsed run containing a firing that stopped for the operator
- **WHEN** the operator looks at the list
- **THEN** the row says a firing is waiting for them
#### Scenario: The conversation being read is not hidden by collapsing

- **GIVEN** a run containing the conversation the operator currently has open
- **WHEN** the list is presented
- **THEN** that conversation is presented rather than collapsed out of view

### Requirement: A firing does not claim a task whose dependencies are unmet

A firing SHALL NOT claim a task the dependency gate would refuse to start. Claimability and
startability must agree, or the loop claims work it cannot begin.

The check SHALL use the same determination of *"are this task's dependencies met"* that the
transition gate uses, so that the queue and the gate cannot disagree.

A firing SHALL claim the queue's oldest startable task, skipping unstartable ones in order rather
than stopping at the first.

#### Scenario: An unstartable task is skipped in favour of a startable one

- **WHEN** a loop's queue holds an older task with an unapproved prerequisite and a newer task with
  none
- **THEN** the firing claims the newer task
- **AND** the older task keeps its status and gains no assignee

#### Scenario: A queue of only unstartable tasks claims nothing

- **WHEN** every non-terminal task in a loop's queue has an unmet dependency
- **THEN** the firing claims nothing

#### Scenario: A task becomes claimable when its prerequisite is approved

- **WHEN** a task's only prerequisite moves to `approved` and the loop fires
- **THEN** the firing claims that task

#### Scenario: The claim and the gate agree

- **WHEN** a firing claims a task
- **THEN** that task's move to `in_progress` is not refused by the dependency gate

### Requirement: A queue gated on unapproved work is stalled, never stopped

A loop whose queue holds only tasks with unmet dependencies SHALL be treated as stalled, and its job
SHALL remain enabled and remain scheduled.

The recorded stall reason SHALL distinguish a queue waiting on work that can still be approved from
one gated on a prerequisite that has been `rejected`, because the two mean different things to an
operator and have different remedies.

A queue gated on a rejected prerequisite SHALL NOT stop the loop. `rejected` is reversible by the
operator, and stopping would set the job disabled and remove it from the scheduler, so the operator
reversing the rejection afterwards could not revive it.

#### Scenario: A dependency-gated queue does not disable the loop

- **WHEN** a loop fires and every task in its queue has an unapproved prerequisite
- **THEN** the job remains enabled and the loop records no stop reason

#### Scenario: The stall reason names which kind of gating it is

- **WHEN** a loop's queue is gated on a prerequisite that is `rejected`
- **THEN** the recorded reason identifies the gating as permanent-until-reversed, distinctly from a
  prerequisite merely not yet approved

#### Scenario: Reversing a rejection revives the loop with no further action

- **WHEN** the operator moves a rejected prerequisite back to `pending`, it is subsequently approved,
  and the loop fires again
- **THEN** the firing claims the task that was gated on it

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

