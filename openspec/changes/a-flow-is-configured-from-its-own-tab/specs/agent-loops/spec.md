## MODIFIED Requirements

### Requirement: An edit to a loop takes effect at its next firing and never during one

The Hub SHALL accept an edit to a loop at any time, including while one of its firings is running,
and SHALL apply that edit at the loop's next firing. This holds for the loop's purpose, its stop
condition, and the agent its job names by default. The next firing is the next time the loop's job
fires, whether or not that firing then starts any work. A firing that finds the loop's agent busy
SHALL apply the edit before asking, but only when none of the loop's own firings is running.
A staged default agent that has been archived by the time the edit is applied SHALL NOT be applied;
the rest of the edit SHALL apply, and the record of its application SHALL say the agent was dropped
and why. Where the loop's summary reports why the loop is not proceeding, it SHALL ask about the
agent the next firing will ask about, which is the staged agent whenever the next firing would apply
it.

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

#### Scenario: A change of default agent waits for the next firing

- **GIVEN** a loop that declares no specification document, whose job names agent A, with a firing in progress under A
- **WHEN** the operator changes the default agent to B
- **THEN** the change is accepted and reported as pending
- **AND** the job still names A while that firing runs, so a Run pressed meanwhile is refused as busy
- **AND** the first firing after it applies B, and the change is no longer reported as pending

#### Scenario: A change of default agent away from an agent that cannot work takes effect

- **GIVEN** a loop that declares no specification document, whose job names agent A, with no firing in progress
- **AND** A's queue is held by a refusal of the provider's usage allowance
- **WHEN** the operator changes the default agent to B, and the loop's job next fires
- **THEN** that firing applies B before it asks whether the loop's agent is busy
- **AND** it proceeds under B rather than being refused because A is held

#### Scenario: An edit applied by a firing that is then refused is recorded as applied

- **GIVEN** a loop with a staged edit and none of its firings running
- **WHEN** its job fires, applies the edit, and is then refused because the loop's agent is busy
- **THEN** the edit is in force and no longer reported as pending
- **AND** its application is recorded against the loop with the actor who staged it

#### Scenario: The loop's summary asks about the agent the next firing will use

- **GIVEN** a loop that declares no specification document, whose job names agent A, with no firing in progress
- **AND** A's queue is held by a refusal of the provider's usage allowance, and a change to agent B is staged
- **WHEN** the operator lists or inspects the loop
- **THEN** the loop is not reported as refused because A is held
- **AND** what it reports is what the next firing, under B, would do

#### Scenario: A staged agent archived before the next firing is dropped

- **GIVEN** a loop whose job names agent A, with a change to agent B and a change of purpose staged
- **AND** B is archived before the loop's job next fires
- **WHEN** the loop's job next fires
- **THEN** the job still names A and the new purpose is in force
- **AND** the record of the edit's application says B was dropped because it is archived

#### Scenario: A change of default agent moves no work

- **GIVEN** a loop whose tasks are assigned to agent A, and input already queued for A
- **WHEN** a change of default agent to B is applied
- **THEN** those tasks keep their assignee and that input stays queued for A
- **AND** the loop's checkpoint lineage is unchanged

### Requirement: A project's loops are listable and individually inspectable

The Hub SHALL let the operator list every loop in a project, whatever its state, and inspect any one
of them individually. A loop's listing entry SHALL carry a label the operator can recognise it by,
the agent its job names, and the specification document it declares, if any, without the caller
having to fetch its job separately.

Listing SHALL be scoped to the project and MUST NOT require naming a conversation, since a loop's
firings each occupy a conversation of their own and none of them is the loop.

#### Scenario: Every loop in a project is listable

- **WHEN** the operator lists a project's loops
- **THEN** every loop is returned regardless of whether it is running, complete, stopped, or archived
- **AND** each carries a label, its agent, the document it declares, its purpose, how it ended if it
  has, and its queue counts

#### Scenario: A loop is inspectable without naming a conversation

- **WHEN** the operator inspects one loop
- **THEN** its queue, current item, firing history, and whether a firing is in progress are returned
- **AND** no conversation identifier is required to make the request

#### Scenario: Archived loops are excluded from the default listing

- **GIVEN** a project with archived and unarchived loops
- **WHEN** the operator lists the project's loops without asking for archived ones
- **THEN** only the unarchived loops are returned

### Requirement: Only a loop's creator, or the operator, may add to its queue directly

The Hub SHALL accept a caller-supplied `loop_id` when creating a task only from that loop's creator
(the agent that created it, or the operator) or from the operator. A loop also has an executor (the
agent its job triggers on each fire) — the same agent MAY be both creator and executor. Every other
caller, including the loop's own executor when it is not also the creator, SHALL be refused, and the
refusal SHALL name `send_message` to the creator as the path to request the addition instead.

This requirement governs only the *creator-authorship* write path above. It does not apply to tasks
a loop's source document materialises on approval, which name no individual caller as their actor.

The Hub records a loop's creator as the agent the loop's job names. Where the operator changes that
agent, the new agent SHALL be the loop's creator from the moment the change is applied, and the
previous agent SHALL NOT be. The change SHALL NOT carry any delegation of control from the previous
agent to the new one, as "A loop has a controller, defaulting to the operator, which may be
delegated" states.

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

#### Scenario: A change of agent moves the creator and not the delegation

- **GIVEN** a loop that has fired, whose job names agent A, with control delegated to its creator
- **WHEN** the operator's change of the job's agent to B is applied
- **THEN** a direct addition by A supplying the loop's id is refused
- **AND** a direct addition by B supplying the loop's id is refused, naming that operator approval is required

### Requirement: A loop has a controller, defaulting to the operator, which may be delegated

The Hub SHALL record for each loop a controller, which decides whether that loop's queue may be
extended, and which SHALL default to the operator.

The operator SHALL be able to delegate control to the loop's creator agent, and to take it back,
after the loop has been created. Where the operator holds control, a request to extend the queue
SHALL be relayed to the operator and SHALL change nothing until the operator decides. Where control
has been delegated, the creator agent SHALL be able to decide the request itself. Each change of
control SHALL be recorded against the loop with the actor responsible and the time it occurred.

A delegation is to the agent that held it. Where a change of the agent the loop's job names is
applied, and that agent is different from the one in force, control SHALL return to the operator,
and the return SHALL be recorded against the loop with the actor who made the change and the time
it was applied. Where the loop's control is delegated, the app SHALL say so before the operator
saves a change of agent.

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

#### Scenario: A change of agent returns control to the operator

- **GIVEN** a loop whose job names agent A, with control delegated to its creator
- **WHEN** the operator changes the default agent to B, and the change is applied
- **THEN** the loop's controller is the operator
- **AND** the return of control is recorded against the loop with the operator as actor and the time it was applied

#### Scenario: Putting the same agent back keeps the delegation

- **GIVEN** a loop whose job names agent A, with control delegated to its creator, and a change to A staged
- **WHEN** the change is applied
- **THEN** control stays delegated

#### Scenario: The operator is told before saving

- **GIVEN** a loop whose control is delegated to its creator
- **WHEN** the operator changes the default agent in the loop's settings, before saving
- **THEN** the app says that control returns to the operator when the change applies

## ADDED Requirements

### Requirement: The operator edits a loop's settings from the loop's own view

The Hub's app SHALL let the operator edit, from a loop's own view, the loop's name, default agent,
message, schedule, purpose and stop condition. The view SHALL state the settings in force, including
the default agent. A change SHALL be sent as only the fields the operator changed, and each SHALL take
effect as the loop's edit rules say: immediately for name, message and schedule, and at the next
firing for purpose, stop condition and default agent.

The declared specification document and whether the loop's work needs evidence SHALL be shown and
MUST NOT be editable there. A loop that has ended or been archived SHALL show its settings read-only.

A stop time SHALL be replaceable there, and SHALL NOT be offered as clearable. The view SHALL refuse
to save a flow whose next firing would have neither a stop time nor a stop when its queue empties,
and SHALL say that a flow needs a stop condition. The view SHALL say that a change of default agent
does not move tasks already assigned, so that a new agent takes only work nobody holds.

#### Scenario: The operator changes a flow's cadence and default agent

- **GIVEN** a running flow whose job names agent A and fires every 5 minutes
- **WHEN** the operator opens the flow's view, edits the cadence to every 15 minutes and the default agent to B, and saves
- **THEN** the cadence is in force at once
- **AND** the change to B is shown as pending, from the next firing

#### Scenario: An unknown or archived agent is refused

- **GIVEN** a project that has at least one agent on its roster
- **WHEN** the operator saves a default agent that does not exist or is archived
- **THEN** the save is refused with a reason naming the agent
- **AND** nothing about the loop changes

#### Scenario: Putting a staged value back is saved as a change

- **GIVEN** a loop whose job names agent A, with a change to B staged and not yet applied
- **WHEN** the operator opens its settings, which show B as the agent from the next firing, sets A, and saves
- **THEN** the change to A is sent and staged
- **AND** the next firing leaves the loop naming A

#### Scenario: A flow cannot be saved without a stop condition

- **GIVEN** a flow with no stop time, which stops when its queue empties
- **WHEN** the operator unchecks stopping when the queue empties and saves
- **THEN** nothing is sent
- **AND** the view says a flow needs a stop condition

#### Scenario: A stop time is moved, not removed

- **GIVEN** a loop with a stop time
- **WHEN** the operator opens its settings
- **THEN** the stop time can be changed to another time
- **AND** no control offers to remove it, and an emptied field sends no change

#### Scenario: An ended loop's settings are read-only

- **GIVEN** a loop that has ended
- **WHEN** the operator opens its view
- **THEN** its settings are shown with no way to edit them

### Requirement: A change of a job's agent does not resume the old agent's session

When the agent a job names is changed, the Hub SHALL discard the session that job would otherwise
resume, since that session belongs to the previous agent. For a job without a loop the change SHALL
apply at once. For a loop it applies at the next firing, and from then on the job SHALL hold no
session of the previous agent's.

#### Scenario: A resume-mode job starts fresh under its new agent

- **GIVEN** a job with no loop, in resume mode, holding a session from agent A
- **WHEN** its agent is changed to B
- **THEN** its next run is B's and does not resume A's session

#### Scenario: A loop's job holds no session of the old agent's once a new agent applies

- **GIVEN** a loop whose job holds a session from agent A, with a change to B staged
- **WHEN** the loop's job next fires and applies B
- **THEN** the job holds no session of A's

### Requirement: Only the operator changes which agent a job names

The Hub SHALL refuse a change to the agent a job names when the request comes from an agent's run,
and SHALL say that only the operator can make it. Other fields an agent may already edit on the same
route are unaffected.

A job's agent decides who works it, and for a loop whose queue control is delegated to its creator,
who may add to that queue. An agent that could rename a job's agent could take both for itself.

#### Scenario: An agent's run cannot re-point a loop

- **GIVEN** a project that allows agents to manage jobs, and a loop whose job names agent A
- **WHEN** a run of agent B asks to change that job's agent to B
- **THEN** the request is refused, saying only the operator can change which agent a job names
- **AND** the job still names A and nothing is staged
