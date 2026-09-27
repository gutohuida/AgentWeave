## ADDED Requirements

### Requirement: Approving a document creates the flow its delivery declares

When the operator approves a change document whose delivery declares a flow, the Hub SHALL create a
flow declaring that document, with the operator as the actor, named after the document, using the
delivery's default agent, stop condition and schedule, and owning the tasks the approval created. The
flow's first firing SHALL be at its next scheduled time. Creating it SHALL NOT depend on the project
allowing agents to create scheduled work, since the operator is the actor.

A delivery's agent is usable only when it is an open agent on the project. The Hub SHALL NOT create a
flow naming an agent that is archived or that the project does not have, whatever else it knows of
that name. When the delivery's agent is not usable, the operator MAY name another agent, or no flow,
at approval. That choice SHALL apply to the flow alone and MUST NOT edit the document.

Where an unarchived flow already declares the document, as on a re-approval after a reopen, the Hub
SHALL NOT create a second one, and the approval SHALL report the existing flow rather than a refusal,
whatever the delivery says. The report SHALL state whether that flow is running, disabled or ended,
and SHALL NOT report a flow that has ended or is disabled as building the document, since no one
works the tasks the approval gave it. An agent the operator chose at such an approval SHALL NOT be
applied, and the report SHALL say that it was not applied because the existing flow already declares
the document. Where the existing flow's agent differs from the delivery's, the report SHALL say so.

The Hub SHALL NOT create a flow whose delivery names no agent or no stop condition, or whose stop
time has already passed, and SHALL report why.

The Hub SHALL NOT create a flow that would own no open task once the approval's tasks are adopted,
as when creating the board failed or every declared task was already served by existing work, since
a flow whose queue was never filled fires an agent turn on every tick and never stops. The approval
SHALL report that no flow was started because it gave the flow no tasks.

If the flow cannot be created, the document SHALL still be approved and its board still created, and
the reason SHALL be reported with the approval.

#### Scenario: Approval starts the declared flow at its next tick

- **GIVEN** a proposed document whose delivery is a flow with agent dev, stopping when its queue empties, every 5 minutes
- **WHEN** the operator approves it
- **THEN** a flow declaring the document exists, naming dev, and holds the tasks the approval created
- **AND** it has not fired; its next run is the next 5-minute boundary

#### Scenario: A flow that cannot be created does not block approval

- **GIVEN** a proposed document whose delivery names an agent that has since been archived
- **WHEN** the operator approves it without choosing another agent
- **THEN** the document is approved and its board is created
- **AND** no flow is created, and the approval reports that the agent is archived

#### Scenario: An agent the project does not have is not given a flow

- **GIVEN** a proposed document whose delivery names an agent that is not one of the project's agents
- **WHEN** the operator approves it
- **THEN** the document is approved and no flow is created
- **AND** the approval reports that the agent is not on the project

#### Scenario: The operator replaces a stale agent at approval

- **GIVEN** a proposed document whose delivery names an archived agent
- **WHEN** the operator approves it choosing agent dev
- **THEN** the flow is created naming dev
- **AND** the document still names the archived agent, and the approval records the replacement

#### Scenario: Re-approval does not create a second flow

- **GIVEN** an approved document whose delivery created flow F, reopened and proposed again
- **WHEN** the operator approves it
- **THEN** no second flow is created, and the tasks the approval created belong to F
- **AND** the approval reports that F already builds the document

#### Scenario: Re-approval after the flow has ended says the new tasks wait

- **GIVEN** an approved document whose flow F stopped when its queue emptied and is not archived
- **WHEN** the document is reopened, revised with a new task, proposed and approved
- **THEN** no second flow is created
- **AND** the approval reports that F has ended and that the new task waits for it

#### Scenario: A replacement agent is not applied to an existing flow

- **GIVEN** an approved document whose flow F names agent dev, reopened and proposed again, whose delivery now names an archived agent
- **WHEN** the operator approves it choosing agent qa
- **THEN** no flow is created and F still names dev
- **AND** the approval reports that qa was not applied because F already declares the document

#### Scenario: An approval that gives the flow no tasks starts no flow

- **GIVEN** a proposed document whose delivery is a flow, and whose board cannot be created
- **WHEN** the operator approves it
- **THEN** the document is approved and no flow is created
- **AND** the approval reports that no flow was started because the approval gave it no tasks

#### Scenario: A delivery of no flow creates none

- **GIVEN** a proposed document whose delivery says no flow
- **WHEN** the operator approves it
- **THEN** its board is created and no flow is created
