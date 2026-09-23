## ADDED Requirements

### Requirement: A document's rigor history is on its screen, and the app records why

The operator's view of a document SHALL show every rigor change recorded for it — the previous and new level, who made it, the reason, and when — and the operator's interface SHALL ask for a reason whenever it changes a document's rigor, and SHALL NOT submit a demotion without one.

Demotion is the operator's legitimate way past a gate because it is recorded. A record nobody can
read, or one whose reason is always blank because the interface never asked, is the unrecorded
override the gate exists to rule out, in a different form.

#### Scenario: The history is shown with the document

- **WHEN** a document's rigor has been changed twice
- **THEN** its view lists both changes, newest first, each with its levels, actor, reason and time

#### Scenario: A demotion from the app carries its reason

- **WHEN** the operator lowers a document's rigor in the app
- **THEN** the interface asks why
- **AND** the change is not submitted until a reason is given
- **AND** the recorded change carries that reason

#### Scenario: A promotion may be given a reason

- **WHEN** the operator raises a document's rigor in the app
- **THEN** the interface offers a reason field
- **AND** the change can be submitted with it left empty
