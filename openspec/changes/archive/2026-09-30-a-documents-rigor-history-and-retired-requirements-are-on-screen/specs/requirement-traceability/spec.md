## ADDED Requirements

### Requirement: A retired requirement stays reachable from its document

The operator's view of a document SHALL list the requirements that document has retired, and from each SHALL reach the tasks and evidence still linked to it and its coverage.

A removed requirement is retired rather than deleted so that its links and evidence survive. Coverage
excludes retired requirements, so without this list a retired requirement leaves every screen while
work still points at it, and the record kept on purpose cannot be read.

#### Scenario: Retired requirements are listed

- **WHEN** a document has retired a requirement
- **THEN** its view lists that requirement's identifier and key as retired

#### Scenario: The work still linked to a retired requirement is reachable

- **WHEN** the operator opens a retired requirement that a task and a piece of evidence still point at
- **THEN** the task and the evidence are shown
- **AND** its coverage is shown as reported for that requirement
