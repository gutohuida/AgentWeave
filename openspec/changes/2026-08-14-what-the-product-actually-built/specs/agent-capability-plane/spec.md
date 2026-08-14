# agent-capability-plane

## ADDED Requirements

### Requirement: An agent can read a specification document

The system SHALL provide an agent with a way to read a specification document, and that capability
SHALL be described in the surface the agent is told it has.

Documents are written into the project's own directory, while a working agent's checkout is an
isolated one branched before the document existed. An agent is therefore told which document governs
its work and, without this, has no way to open it — leaving it to implement from another agent's
paraphrase, with no way to detect divergence from what was approved.

The document SHALL be returned as structured content rather than as its rendered form. The rendering
exists for a person; returning it spends an agent's context on markup and leaves it to re-derive
what the structure already states.

Each requirement returned SHALL carry the identifier the system minted for it, so that an agent
quotes the same identifier that tasks, evidence and gates use.

Acceptance criteria SHALL be returned grouped under the requirement they demonstrate, rather than as
a separate list to be joined by the reader.

Reading SHALL be permitted in every phase. Reading is not authoring, and every gate in this area
governs writing or approving. A capability that is refused depending on state is one an agent
concludes it does not have.

The document's phase SHALL be returned, so that how settled it is can be judged rather than assumed.

Content that cannot be matched to a minted identifier SHALL still be returned, accompanied by a
statement of the problem. A document carrying no structured content SHALL be reported as such rather
than as a document with no requirements.

#### Scenario: An agent reads the document it is implementing

- **WHEN** an agent reads a specification document by path
- **THEN** it receives the requirements with their identifiers, statements and obligations
- **AND** each requirement carries its own acceptance criteria
- **AND** the document's phase is stated

#### Scenario: Reading is allowed before approval

- **WHEN** an agent reads a document that has not been approved
- **THEN** the document is returned
- **AND** its phase says it is not approved

#### Scenario: A document with no structured content is reported honestly

- **WHEN** an agent reads a document carrying no structured content
- **THEN** the response states that, rather than reporting an empty set of requirements

#### Scenario: The capability appears in the described surface

- **WHEN** an agent is told what it can do
- **THEN** reading a specification document is among the capabilities described

### Requirement: A task states what its requirements say

A task SHALL carry, for each requirement it serves, the wording of that requirement as the document
currently states it, alongside its identifier.

An identifier and a location within a document are only actionable by a reader that can open the
document. Carrying the wording makes a task independently actionable, and is what a task's own
description must otherwise duplicate and can then contradict.

The wording SHALL be read from the document rather than stored alongside the requirement's identity,
so that it cannot come to disagree with what the document says.

Reading the wording SHALL NOT be per task: a board serving many tasks from one document SHALL read
that document once.

Where the wording cannot be obtained, the task SHALL still be returned with its identifiers. A task
board SHALL NOT fail because a project's directory is unavailable.

#### Scenario: A task carries its requirements' wording

- **WHEN** a task serving requirements is read
- **THEN** each requirement's current statement is present alongside its identifier

#### Scenario: An unavailable document does not fail the board

- **WHEN** tasks are read and the project's directory cannot be reached
- **THEN** the tasks are returned with their identifiers
- **AND** no error is raised
