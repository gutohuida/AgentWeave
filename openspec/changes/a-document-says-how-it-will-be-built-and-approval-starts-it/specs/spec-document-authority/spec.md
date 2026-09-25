## ADDED Requirements

### Requirement: A change document declares how it will be built before it is proposed

A change document's payload SHALL carry a delivery section stating how its work will be built: either
by a flow, naming the flow's default agent, at least one stop condition and a schedule, or by no flow.
The Hub SHALL refuse to propose a change document whose delivery is absent, or whose flow delivery
names no agent or no stop condition, stating what is missing. "No flow" SHALL be a complete answer.

The delivery section MUST NOT be required for a document to be saved, re-rendered, approved or
merged, so that a document written before the section existed keeps working. At approval an absent
delivery SHALL mean no flow.

#### Scenario: Proposing without a delivery is refused

- **GIVEN** a change document with requirements and tasks but no delivery section
- **WHEN** it is proposed
- **THEN** the proposal is refused with a finding saying how the work will be built is unanswered

#### Scenario: A flow delivery without a stop condition is refused

- **GIVEN** a change document whose delivery is a flow naming an agent and no stop condition
- **WHEN** it is proposed
- **THEN** the proposal is refused with a finding naming the missing stop condition

#### Scenario: No flow is a complete answer

- **GIVEN** a change document whose delivery says no flow
- **WHEN** it is proposed and nothing else blocks it
- **THEN** it is proposed

#### Scenario: A document from before the section stays approvable

- **GIVEN** a document proposed before delivery sections existed
- **WHEN** the operator approves it
- **THEN** it is approved, its board is created, and no flow is created

### Requirement: The exploring interview asks how the change will be built

While a change document is being explored, the authoring agent SHALL be instructed to ask the operator
how the change will be built, recommending a flow where the work splits into tasks and stating what a
flow does. If the operator chooses a flow, the agent SHALL be instructed to ask for its default agent,
its stop condition and its schedule. The agent SHALL be told the project's open agents by name, whether
or not the project has more than one. The question SHALL be asked in the reply, like the rest of the
interview.

#### Scenario: A single-agent project's author can name an agent

- **GIVEN** a project whose only open agent is the author
- **WHEN** the author's exploring turn starts
- **THEN** its context names the project's open agents, the author among them
- **AND** it is instructed to ask how the change will be built

### Requirement: A document's delivery is checked against the roster when it is read

Where a document not yet approved declares a flow delivery, the Hub SHALL report on each read whether
the named default agent is an open agent on the project, and SHALL report it as stale, with the reason,
when the agent is archived or does not exist. The report MUST NOT be written into the document, since
the roster changes independently of it. The app SHALL show a stale delivery beside the approval action.

#### Scenario: An archived agent makes the delivery stale

- **GIVEN** a proposed document whose delivery names agent dev2
- **WHEN** dev2 is archived and the document is read
- **THEN** the delivery is reported stale because dev2 is archived
- **AND** the document's file is unchanged
