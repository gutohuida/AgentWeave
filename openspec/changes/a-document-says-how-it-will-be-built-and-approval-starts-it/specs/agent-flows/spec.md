## ADDED Requirements

### Requirement: Approving a document creates the flow its delivery declares

When the operator approves a change document whose delivery declares a flow, the Hub SHALL create a
flow declaring that document, with the operator as the actor, named after the document, using the
delivery's default agent, stop condition and schedule, and owning the tasks the approval created. The
flow's first firing SHALL be at its next scheduled time. Creating it SHALL NOT depend on the project
allowing agents to create scheduled work, since the operator is the actor.

When the delivery's agent is not usable, the operator MAY name another agent, or no flow, at approval.
That choice SHALL apply to the flow alone and MUST NOT edit the document.

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

#### Scenario: The operator replaces a stale agent at approval

- **GIVEN** a proposed document whose delivery names an archived agent
- **WHEN** the operator approves it choosing agent dev
- **THEN** the flow is created naming dev
- **AND** the document still names the archived agent, and the approval records the replacement

#### Scenario: A delivery of no flow creates none

- **GIVEN** a proposed document whose delivery says no flow
- **WHEN** the operator approves it
- **THEN** its board is created and no flow is created
