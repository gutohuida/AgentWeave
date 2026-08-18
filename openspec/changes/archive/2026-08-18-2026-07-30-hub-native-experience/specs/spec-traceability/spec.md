## ADDED Requirements

### Requirement: Every requirement carries a stable, visible identifier

Each requirement in a specification SHALL carry an identifier that is visible in the document,
citable outside the tool, and stable for the life of that requirement.

An identifier SHALL survive edits to the requirement's title, its wording, its position in the
document, and the document's relocation within the project. An identifier MUST NOT be reused for a
different requirement, including after the original is retired.

A requirement without an identifier MUST NOT be silently ignored; it SHALL be reported as
unidentified so it can be assigned one.

#### Scenario: An identifier survives rewriting and relocation

- **WHEN** a requirement's title and wording are rewritten, and it is moved to another position or
  another document in the same project
- **THEN** its identifier is unchanged
- **AND** the work and evidence linked to it remain linked

#### Scenario: Identifiers are citable outside the tool

- **WHEN** an identifier is quoted in a commit message, a conversation, or any external record
- **THEN** it unambiguously designates one requirement

#### Scenario: A retired identifier is not reissued

- **WHEN** a requirement is retired and a new requirement is added afterwards
- **THEN** the new requirement receives an identifier that has never been used

#### Scenario: An unidentified requirement is reported

- **WHEN** a document contains a requirement with no identifier
- **THEN** it is reported as unidentified
- **AND** it is not treated as satisfied

### Requirement: Work declares the requirements it serves

A task SHALL be able to declare the requirements it serves. The declaration SHALL persist after the
task completes, so that the record of why work was done outlives the doing of it.

A requirement that no work references SHALL be distinguishable from one whose work is merely
incomplete.

#### Scenario: A task names its requirements

- **WHEN** a task declares the requirements it serves
- **THEN** those requirements list that task among the work serving them

#### Scenario: The link outlives the task

- **WHEN** a task that served a requirement is completed or archived
- **THEN** the requirement still records that the task served it

#### Scenario: Unserved requirements are visible

- **WHEN** a requirement has no work referencing it
- **THEN** it is reported as unserved, distinctly from a requirement whose work is unfinished

### Requirement: Evidence attaches to requirements and names its origin

A requirement SHALL be able to carry evidence that it is satisfied. Each piece of evidence SHALL
identify what it is, what produced it, and when.

Evidence SHALL be attributable to the agent or operator and the run that produced it. Evidence
MUST NOT be recorded without an origin.

#### Scenario: Evidence records what produced it

- **WHEN** evidence is attached to a requirement
- **THEN** it identifies its kind, its origin, and the time it was produced
- **AND** it names the agent or operator and the run responsible

#### Scenario: Evidence cannot be anonymous

- **WHEN** evidence is offered without an identifiable origin
- **THEN** it is refused

### Requirement: Every requirement has an observable verification state

Each requirement SHALL present a verification state derived from the work and evidence linked to it.
The state SHALL distinguish at least: not started, in progress, evidence awaiting review, and
verified.

The state SHALL be visible where the requirement is read, not only in a separate report.

A requirement SHALL NOT be shown as verified on the strength of an agent's assertion alone; verified
means evidence exists and, where the document requires it, has been accepted.

#### Scenario: State is visible in the document

- **WHEN** an operator reads a specification
- **THEN** each requirement's verification state is visible alongside it

#### Scenario: State follows the evidence

- **WHEN** work is linked to a requirement and evidence is later attached
- **THEN** the requirement moves from not started, to in progress, to evidence awaiting review

#### Scenario: An assertion is not verification

- **WHEN** an agent reports that a requirement is satisfied without evidence
- **THEN** the requirement is not shown as verified

### Requirement: Changing a requirement invalidates evidence that predates the change

When a requirement's meaning changes, evidence produced before that change SHALL become stale rather
than continuing to count as verification.

Stale evidence SHALL be distinguishable from absent evidence, and its history SHALL be retained
rather than deleted, so the reason a requirement regressed remains legible.

An operator MAY record that a change was editorial and that existing evidence still holds.

#### Scenario: A substantive edit stales the evidence

- **WHEN** a verified requirement's meaning is changed
- **THEN** its evidence becomes stale and it is no longer shown as verified

#### Scenario: Stale is not the same as missing

- **WHEN** a requirement has stale evidence
- **THEN** it is distinguished from a requirement that never had evidence
- **AND** the superseded evidence remains inspectable

#### Scenario: An editorial change may preserve verification

- **WHEN** an operator records a change as editorial
- **THEN** existing evidence continues to hold and the requirement remains verified

### Requirement: Drift between specification and implementation is surfaced

The system SHALL report divergence where implementation linked to a requirement changes without
any corresponding change to that requirement.

Drift SHALL be presented as a diagnostic to be resolved — by updating the requirement, by recording
that none was needed, or by correcting the implementation — and MUST NOT silently alter either
artifact.

#### Scenario: Implementation moving alone is reported

- **WHEN** implementation linked to a requirement changes and the requirement does not
- **THEN** the divergence is reported against that requirement

#### Scenario: Drift is resolved deliberately

- **WHEN** an operator resolves reported drift
- **THEN** the resolution is recorded as updating the requirement, correcting the implementation, or
  accepting that no change was needed

#### Scenario: Nothing is changed automatically

- **WHEN** drift is detected
- **THEN** neither the requirement nor the implementation is modified without an explicit action

### Requirement: Traceability is navigable in both directions

From a requirement it SHALL be possible to reach the work and evidence serving it. From a piece of
work it SHALL be possible to reach the requirements it served.

#### Scenario: From requirement to work

- **WHEN** an operator selects a requirement
- **THEN** the work and evidence linked to it are reachable

#### Scenario: From work to requirement

- **WHEN** an operator examines a task or a completed run
- **THEN** the requirements it served are reachable

### Requirement: A project reports its verification coverage

A project SHALL report, across its specifications, how many requirements are verified, awaiting
review, in progress, unserved, stale, or drifting.

This report SHALL be derived from the same state shown on individual requirements, so that a summary
can never disagree with the documents it summarises.

#### Scenario: Coverage is reportable

- **WHEN** an operator asks how a project stands against its specifications
- **THEN** the counts of verified, awaiting review, in progress, unserved, stale, and drifting
  requirements are reported

#### Scenario: Summary and document agree

- **WHEN** a requirement's state changes
- **THEN** the project's reported coverage reflects it
