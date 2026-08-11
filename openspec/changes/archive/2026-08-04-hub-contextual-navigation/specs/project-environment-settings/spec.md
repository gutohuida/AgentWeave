## ADDED Requirements

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
