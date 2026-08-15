# project-environment-settings Specification

## Purpose
The project's own configuration surface: how a section states what it governs, how settings are
presented as rows rather than boxes, and how saving reports its outcome.

Introduced by `2026-08-04-hub-contextual-navigation`, which moved per-project configuration out of
the navigation rail and needed somewhere to say what that surface owes the operator once it is no
longer a menu.
## Requirements
### Requirement: A configuration section states what it governs

Every configuration section SHALL open with its own title and a short statement of what it governs,
so that a section holding few settings still reads as complete rather than unfinished.

#### Scenario: A sparse section still reads as deliberate

- **WHEN** the operator opens a configuration section containing only a few settings
- **THEN** the section shows its title and a statement of what it governs
- **AND** its settings are grouped and separated rather than floating in empty space

### Requirement: Settings are presented as labelled rows, not as boxed cards

A configuration section SHALL present its settings as a sequence of rows. Each row SHALL pair its
label, and an explanation of what the setting does, with the control that changes it. Rows SHALL be
separated from one another by a hairline rather than each being enclosed in its own bounded card.

#### Scenario: A setting explains itself in place

- **WHEN** the operator reads a setting row
- **THEN** its label and an explanation of its effect are shown beside the control that changes it

#### Scenario: Rows are separated without being boxed

- **WHEN** a section's settings are displayed
- **THEN** consecutive rows are separated by a hairline
- **AND** no row is enclosed in its own card

### Requirement: A configuration section occupies the content region

A configuration section SHALL fill the content region it is given. Text and controls SHALL be
bounded to a readable measure, but a section MUST NOT leave a large unused region beside a column
narrower than the space available to it.

#### Scenario: No dead region beside the settings

- **WHEN** a configuration section is displayed at a wide viewport
- **THEN** the section occupies the content region
- **AND** no substantial area of the content region is left visibly unused beside it

### Requirement: Numeric fields are typed, not stepped

A numeric setting SHALL be entered by typing. Increment and decrement stepper buttons MUST NOT be
rendered, in any browser engine.

Removing the steppers MUST NOT remove the field's numeric constraints; invalid values SHALL still be
rejected with an explanation.

#### Scenario: No stepper buttons are drawn

- **WHEN** the operator focuses or hovers a numeric setting
- **THEN** no increment or decrement button is shown

#### Scenario: Constraints survive

- **WHEN** the operator types a value outside a numeric setting's permitted range and saves
- **THEN** the value is rejected
- **AND** the operator is told what is permitted

### Requirement: Saving reports its outcome

Changing a configuration section's settings SHALL report whether the change was saved, and a failure
SHALL state why in the section rather than only in a log.

#### Scenario: A successful save is acknowledged

- **WHEN** the operator saves a valid change
- **THEN** the interface confirms the change was saved

#### Scenario: A rejected save explains itself

- **WHEN** a save is rejected
- **THEN** the reason is shown in the section
- **AND** the operator's entered values are preserved for correction

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

