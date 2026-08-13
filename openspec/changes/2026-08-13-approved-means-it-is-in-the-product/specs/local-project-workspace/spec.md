# local-project-workspace

## ADDED Requirements

### Requirement: A project's main branch is named, not inferred

A project SHALL carry an explicit main branch setting, and the system SHALL NOT write to a branch it
inferred.

Where the setting is absent, the system SHALL NOT merge. Inferring a branch name is acceptable for a
read-only report, whose worst outcome is an `unknown` answer, and is not acceptable for an operation
that writes commits — a wrong inference there places work in a branch the operator did not choose.

The system MAY detect a likely main branch and offer it to the operator to confirm when a project is
set up or first configured. A detected name SHALL NOT take effect until the operator has accepted it.

An absent setting SHALL NOT be treated as an error, SHALL NOT block any task transition, and SHALL
NOT change how integration is reported for projects that have not set one. Existing projects
therefore keep their current coverage answers until an operator chooses a branch.

#### Scenario: An unset main branch prevents merging but nothing else

- **WHEN** a project has no main branch configured
- **THEN** no merge is performed for any approval
- **AND** task transitions behave exactly as they did before the setting existed
- **AND** integration continues to be reported as it was

#### Scenario: A detected branch is a suggestion

- **WHEN** the system detects a likely main branch for a project
- **THEN** it is offered to the operator
- **AND** it does not become the merge target until the operator accepts it

#### Scenario: Reporting is unaffected by the setting's absence

- **WHEN** coverage reports integration for a project with no configured main branch
- **THEN** the answer is the same as it was before this capability existed
