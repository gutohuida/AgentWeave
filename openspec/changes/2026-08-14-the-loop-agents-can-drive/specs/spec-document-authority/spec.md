# spec-document-authority

## ADDED Requirements

### Requirement: A declared task can state the name the board shows

A document declaring a task SHALL be able to state that task's title, and the system SHALL use it when the task is created.

A declared task carries a description of the work — a sentence of intent, written to be read in the
document. A board shows names. Deriving one from the other produces a title that is the whole
sentence, which is not a name, and a board of them cannot be scanned.

Where no title is declared, the system SHALL derive one, and SHALL keep it short enough to read as a
name. A derived title SHALL NOT end mid-word: a truncation that splits a word reads as a defect in
the board rather than as an abbreviation.

A description short enough to serve as a name SHALL be used unchanged. Shortening what is already
short would be a change with no reader.

#### Scenario: A declared title is used

- **WHEN** a document declares a task with a title
- **AND** the document is approved
- **THEN** the created task carries that title

#### Scenario: A title is derived when none is declared

- **WHEN** a declared task states only its description
- **THEN** the created task carries a title derived from it
- **AND** that title is short enough to read as a name

#### Scenario: A derived title does not split a word

- **WHEN** a description is too long to serve as a title
- **THEN** the derived title ends on a word boundary

#### Scenario: A short description is kept as-is

- **WHEN** a declared task's description is already short enough to be a name
- **THEN** the created task's title is that description
