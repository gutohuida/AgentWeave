## ADDED Requirements

### Requirement: Drift is raised and answered where the operator reads the requirement

The operator's view of a specification document SHALL offer a scan for drift, SHALL show that document's open drift candidates, and SHALL let the operator answer each one there.

A state whose remedy cannot be performed on the surface that shows it is a defect even when the
state is correct. The coverage of a document already reports *drifting* and the approval gate
already names answering the candidate as the way through; both SHALL be performable without an
HTTP client.

Raising and answering SHALL ship together. A scan with no way to answer would make one call enough to
leave a `gate` requirement permanently unapprovable, because a scan never raises the same question
twice and so cannot undo itself.

Each candidate SHALL be shown with the requirement's identifier, the files that moved, and the
evidence that had been verified. A candidate SHALL be answered once: an answer to a candidate that is
no longer open SHALL be refused, naming the answer it already has. Scanning and answering SHALL be
announced to every open view of the project.

The approval gate's refusal for a drifting requirement SHALL say that the operator answers it and
where, and that an agent cannot.

#### Scenario: The operator scans from the document

- **WHEN** the operator scans for drift from a document's view
- **THEN** the scan runs across the project
- **AND** the view reports how many candidates were raised, and how many belong to this document

#### Scenario: A candidate is answered where it is shown

- **WHEN** a document has an open drift candidate
- **THEN** its view shows the requirement's identifier, the files that moved and the evidence that
  was verified
- **AND** the operator can answer it as specification updated, implementation corrected, or no change
  required

#### Scenario: Answering clears drifting

- **WHEN** the operator answers the only open candidate for a requirement
- **THEN** the requirement no longer reports drifting in that view or in any other open view

#### Scenario: A candidate is not answered twice

- **WHEN** an answer is submitted for a candidate that has already been answered
- **THEN** it is refused
- **AND** the refusal names the answer already recorded
- **AND** the recorded answer is unchanged

#### Scenario: The gate's remedy names who can perform it

- **WHEN** approval is refused because a gated requirement is drifting
- **THEN** the refusal says that the operator answers the drift candidate on the document
- **AND** it says that an agent cannot answer it
