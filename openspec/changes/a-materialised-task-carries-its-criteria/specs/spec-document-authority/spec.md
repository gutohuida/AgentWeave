# spec-document-authority

## ADDED Requirements

### Requirement: A materialised task carries the criteria of the requirements it serves

When a declared task is materialised, the system SHALL attach to it the acceptance criteria of every requirement that task resolves, and SHALL attach no others.

A document states its acceptance criteria once, against requirements, and its tasks against the same
requirements. The link between them is already known at the moment the task is created: the
materialising step has resolved that entry's requirements in order to link them. Leaving the
criteria behind means the standard exists in the document and is absent everywhere the work is
actually done or checked.

The consequence is not a missing convenience. The turn composed for a task renders its acceptance
criteria to the agent holding it and to the agent reviewing it, and introduces them to a reviewer as
the standard to check the work against. A task with none presents that introduction followed by
nothing, and the standard is re-derived from the code instead of read.

Criteria SHALL be attached in a form the existing readers of that field already accept, so that
stating the standard does not require a change to how it is displayed or consumed.

A task that resolves no requirement SHALL carry no criteria, and this SHALL NOT be an error: a
declared task may legitimately name no requirement, and inventing a standard for it would assert
something the document did not say.

Attaching criteria SHALL NOT change which tasks are created, their identity, or their titles.

An attached criterion that declares a handle SHALL carry it, so that anything later reporting on one can say which it was.

A criterion that arrives unidentifiable cannot be matched back to the document, and nothing that
already exists can recover the link afterwards — a task's criteria can only be set when the task is
created, so what is lost here is lost permanently. Where a document declares no handle for a
criterion, the criterion SHALL still be attached: its statement is the part the work is judged
against, and withholding it to punish a missing handle would trade the standard for the label.

A criterion that states no starting state, no event and no outcome SHALL NOT be attached. It carries
no standard, and presenting it to a reader as though it did is worse than its absence.

A document whose acceptance criteria cannot be read SHALL still have its declared tasks created.
Criteria state a standard for work; failing to read them is a reason to create the work without its
standard, never a reason to create less of the work than the document declared.

#### Scenario: A task's criteria follow its requirements

- **WHEN** a document declares a task naming a requirement
- **AND** that document declares an acceptance criterion against the same requirement
- **AND** the document is approved
- **THEN** the created task carries that criterion

#### Scenario: Criteria belonging to other requirements are not attached

- **WHEN** a document declares a task naming one requirement
- **AND** the document declares criteria against that requirement and against a different one
- **AND** the document is approved
- **THEN** the created task carries only the criteria of the requirement it names

#### Scenario: A task naming several requirements carries all their criteria

- **WHEN** a declared task names more than one requirement
- **AND** each has at least one acceptance criterion
- **AND** the document is approved
- **THEN** the created task carries the criteria of every requirement it names

#### Scenario: A task naming no requirement carries no criteria

- **WHEN** a document declares a task that names no requirement
- **AND** the document is approved
- **THEN** the created task is created with no acceptance criteria
- **AND** the approval is not refused

#### Scenario: A requirement with no criteria contributes nothing

- **WHEN** a declared task names a requirement that has no acceptance criterion
- **AND** the document is approved
- **THEN** the created task carries no criteria from that requirement
- **AND** the approval is not refused

#### Scenario: The attached criterion is readable where criteria are already shown

- **WHEN** a task created from a document carries acceptance criteria
- **THEN** each criterion is rendered to a reader as text, in the same place a task's acceptance criteria were already shown
- **AND** no reader of that field has to interpret a new shape to display it

#### Scenario: A criterion states its starting state, its event and its outcome

- **WHEN** a criterion declared with a starting state, an event and an observable outcome is attached to a task
- **THEN** all three are present in what the task carries
- **AND** the outcome is not discarded in favour of the event alone

#### Scenario: An attached criterion says which criterion it is

- **WHEN** a document declares two criteria against the same requirement, each with its own handle
- **AND** a task naming that requirement is created
- **THEN** each attached criterion carries the handle the document gave it
- **AND** the two are distinguishable from one another without re-reading the document

#### Scenario: A criterion with no handle is still attached, and says nothing false about its identity

- **WHEN** a document declares a criterion with a starting state, an event and an outcome but no handle
- **AND** a task naming its requirement is created
- **THEN** the criterion is attached with its starting state, event and outcome
- **AND** nothing in what the task carries presents a handle the document did not declare

#### Scenario: A criterion stating nothing is not attached

- **WHEN** a document declares a criterion against a requirement with no starting state, no event and no outcome
- **AND** a task naming that requirement is created
- **THEN** that criterion is not among the task's criteria
- **AND** the task is still created

#### Scenario: Unreadable criteria do not cost the document its tasks

- **WHEN** a document declares several tasks
- **AND** its acceptance criteria cannot be read
- **THEN** every task the document declares is still created
- **AND** those tasks carry no criteria

#### Scenario: Attaching criteria changes nothing about which tasks exist

- **WHEN** two documents declare the same tasks against the same requirements, and one declares acceptance criteria while the other declares none
- **AND** both are approved
- **THEN** each creates the same number of tasks, with the same titles and the same declared keys
- **AND** the tasks differ only in the criteria they carry
