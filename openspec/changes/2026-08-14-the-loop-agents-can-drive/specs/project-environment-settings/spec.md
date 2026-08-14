# project-environment-settings

## ADDED Requirements

### Requirement: The operator can choose the branch approval merges into

The system SHALL offer the operator a control for choosing the project's main branch, in the place it tells them to look for one.

Nothing merges until a branch is chosen, and the system already says so — it tells the operator to
choose one in the project's settings. A message pointing at a control that does not exist is a
closed loop: the operator is told what to do and given no way to do it.

The system SHALL offer a detected branch as a suggestion. Detection is safe for a report and unsafe
for a write, so a suggestion takes effect only once the operator submits it.

A project that is not a repository SHALL be handled without offering a choice that cannot apply.

#### Scenario: The operator chooses a main branch

- **WHEN** the operator opens the project's settings
- **THEN** a main-branch control is present
- **AND** it offers the detected branch as a suggestion

#### Scenario: A suggestion is not an assignment

- **WHEN** a branch is detected and the operator has chosen nothing
- **THEN** the project still has no main branch
- **AND** nothing merges

#### Scenario: The integration message points somewhere real

- **WHEN** work is not merged because no main branch is set
- **AND** the operator follows the message to the project's settings
- **THEN** the control it names is there

### Requirement: Settings may be changed one at a time

The system SHALL accept a settings change that names only the fields being changed, leaving the rest as they were.

A surface that must resend every setting to change one is a surface that can silently revert a
setting it did not know about — which is how a save cleared a project's entire checkpoint
configuration.

Omitting a field SHALL mean "unchanged", and SHALL remain distinguishable from clearing it
deliberately.

Validation that spans more than one field SHALL be applied to the resulting settings, not to the
change alone. A change carrying half of a paired setting is valid when the other half is already
stored.

#### Scenario: One field is changed

- **WHEN** a settings change names only the main branch
- **THEN** the main branch changes
- **AND** every other setting keeps its value

#### Scenario: Half a paired setting is accepted when the other half is stored

- **WHEN** a settings change names only one of two fields that are validated together
- **AND** the stored settings already carry the other
- **THEN** the change is accepted

#### Scenario: Clearing is still expressible

- **WHEN** a settings change names a field with an empty value
- **THEN** that field is cleared rather than left unchanged
