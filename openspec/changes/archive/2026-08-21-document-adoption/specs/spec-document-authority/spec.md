## ADDED Requirements

### Requirement: A document may enter Hub tracking without being created through the Hub

The Hub SHALL recognise that a specification document can exist before its `spec_documents` row
does, and SHALL provide a way for such a document to become tracked without being rewritten.
Creating a document through the Hub and adopting one that already exists are distinct acts: the
first writes a starter file and takes its identity from the caller, the second writes nothing and
takes its identity from the file.

#### Scenario: Creating a document still writes a starter file

- **WHEN** the operator creates a new document at a path where no file exists
- **THEN** a row is created and a starter file is written at that path
- **AND** the document's title and kind are those the caller supplied

#### Scenario: Adopting a document takes its identity from the file

- **WHEN** the operator adopts a document at a path where a file already exists
- **THEN** a row is created whose title and kind come from the file's own payload
- **AND** the file is not written

#### Scenario: Creation is refused where a document is already tracked

- **WHEN** the operator creates a document at a path that already has a row
- **THEN** the creation is refused, as it is today

### Requirement: The file is authoritative at the point of adoption

At the moment a document enters Hub tracking, the file SHALL be the sole source of that document's
title, kind and phase. This is what allows a project's specification corpus to be reproduced from
its committed files alone on a machine whose database has never seen it.

This authority is scoped to adoption. Once a row exists, the row remains authoritative for phase and
rigor, and a file that has moved underneath it remains drift to be reported rather than silently
accepted.

#### Scenario: A cloned corpus reconstitutes from its files

- **WHEN** a project's `spec/` tree is present with no corresponding `spec_documents` rows, and
  corpus-wide adoption is run
- **THEN** each document is tracked with the title, kind and phase recorded in its own file

#### Scenario: The row stays authoritative after adoption

- **WHEN** an adopted document's file is edited outside the Hub so that its recorded phase differs
  from the row's
- **THEN** the row's phase is unchanged
- **AND** the difference is reported as drift rather than applied

### Requirement: Adoption reports rather than resolves

Where a document's file and its existing row disagree, the Hub SHALL report the disagreement and
SHALL NOT resolve it on the operator's behalf.

#### Scenario: Disagreement is surfaced with both values

- **WHEN** adoption is attempted against a path whose row and file disagree on title, kind or phase
- **THEN** the response names each differing field and reports both the file's value and the row's
  value

#### Scenario: No write follows a disagreement

- **WHEN** adoption reports a disagreement
- **THEN** neither the row nor the file is modified
