# local-project-workspace

## ADDED Requirements

### Requirement: A registered project is seeded with ignore rules for what the system creates

When a project is registered, the system SHALL ensure the project's version control ignores the
working artefacts the system itself creates in that directory.

Agents commit what they find. Without this, the isolated checkouts and caches the system places in
the project directory are committed by the first agent that runs, and the operator inherits them in
their own history having never chosen them.

Seeding SHALL be additive and SHALL NOT remove or reorder rules the operator already has. Ignore
rules are the operator's file; a project being registered is not a reason to rewrite it.

Seeding SHALL be idempotent, so that re-registering a project does not accumulate repeated rules.

A project that is not under version control SHALL be registered unchanged, and this SHALL NOT be an
error.

Failure to seed SHALL NOT fail registration. Ignore rules are a convenience; a project that cannot
receive them is still a project.

#### Scenario: Registering seeds ignore rules

- **WHEN** a project under version control is registered
- **THEN** the system's own working artefacts are ignored

#### Scenario: Existing rules are preserved

- **WHEN** a project with its own ignore rules is registered
- **THEN** those rules remain
- **AND** the system's rules are added alongside them

#### Scenario: Re-registering does not duplicate

- **WHEN** a project is registered again
- **THEN** the ignore rules are not repeated

#### Scenario: A project without version control registers unchanged

- **WHEN** a project not under version control is registered
- **THEN** registration succeeds
- **AND** no ignore file is created
