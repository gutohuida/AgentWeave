## MODIFIED Requirements

### Requirement: An edit to a loop takes effect at its next firing and never during one

The Hub SHALL accept an edit to a loop at any time, including while one of its firings is running,
and SHALL apply that edit at the loop's next firing. This holds for the loop's purpose, its stop
condition, and the agent its job names by default.

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

- **GIVEN** a loop whose job names agent A, with a firing in progress under A
- **WHEN** the operator changes the default agent to B
- **THEN** the change is accepted and reported as pending
- **AND** the job still names A until the next firing, so a Run pressed meanwhile is refused as busy
- **AND** the next firing applies B, and the change is no longer reported as pending

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

## ADDED Requirements

### Requirement: The operator edits a loop's settings from the loop's own view

The Hub's app SHALL let the operator edit, from a loop's own view, the loop's name, default agent,
message, schedule, purpose and stop condition. The view SHALL state the settings in force, including
the default agent. A change SHALL be sent as only the fields the operator changed, and each SHALL take
effect as the loop's edit rules say: immediately for name, message and schedule, and at the next
firing for purpose, stop condition and default agent.

The declared specification document and whether the loop's work needs evidence SHALL be shown and
MUST NOT be editable there. A loop that has ended or been archived SHALL show its settings read-only.

#### Scenario: The operator changes a flow's cadence and default agent

- **GIVEN** a running flow whose job names agent A and fires every 5 minutes
- **WHEN** the operator opens the flow's view, edits the cadence to every 15 minutes and the default agent to B, and saves
- **THEN** the cadence is in force at once
- **AND** the change to B is shown as pending, from the next firing

#### Scenario: An unknown or archived agent is refused

- **WHEN** the operator saves a default agent that does not exist or is archived
- **THEN** the save is refused with a reason naming the agent
- **AND** nothing about the loop changes

#### Scenario: An ended loop's settings are read-only

- **GIVEN** a loop that has ended
- **WHEN** the operator opens its view
- **THEN** its settings are shown with no way to edit them

### Requirement: A plain job's change of agent does not resume the old agent's session

When the agent a job without a loop names is changed, the Hub SHALL apply the change at once and
SHALL discard the session that job would otherwise resume, since that session belongs to the previous
agent.

#### Scenario: A resume-mode job starts fresh under its new agent

- **GIVEN** a job with no loop, in resume mode, holding a session from agent A
- **WHEN** its agent is changed to B
- **THEN** its next run is B's and does not resume A's session
