## ADDED Requirements

### Requirement: A quiet control never gains an outline on hover

A control whose resting state draws no border or outline MUST NOT acquire one on hover.

Hover SHALL be expressed by a change of background fill, text prominence, or icon prominence. This
applies wherever such controls appear, not only within the composer.

A control that draws a border at rest is unaffected and MAY change that border's colour on hover.
Keyboard focus indication is unaffected.

#### Scenario: A borderless control stays borderless when hovered

- **WHEN** the operator hovers a control that draws no border at rest
- **THEN** no border or outline appears
- **AND** its background, text, or icon prominence changes instead

#### Scenario: A bordered control may still respond

- **WHEN** the operator hovers a control that draws a border at rest
- **THEN** that border may change colour

#### Scenario: Focus indication is unaffected

- **WHEN** any control receives keyboard focus
- **THEN** its focus indicator is shown

### Requirement: A project's location is displayed as structure, not as a sentence

The workspace header SHALL present a project's directory as a sequence of distinct path segments,
each an element in its own right. It MUST NOT present the path as a single concatenated string.

The path SHALL occupy its own line and MUST NOT share a line with unrelated project metadata such as
a count of agents.

A path too long for the available width SHALL be elided in the middle, preserving the leading and
trailing segments. The complete path SHALL remain available to the operator. A segment that is not
interactive MUST NOT be styled as though it were.

#### Scenario: Segments are separate elements

- **WHEN** a project with a multi-segment directory is displayed
- **THEN** each segment is a distinct element
- **AND** the path is not a single concatenated string

#### Scenario: The path has its own line

- **WHEN** the workspace header is displayed
- **THEN** the path occupies its own line
- **AND** does not share a line with the agent count

#### Scenario: A deep path elides in the middle

- **WHEN** a path is too long for the available width
- **THEN** it is elided in the middle
- **AND** its leading and trailing segments remain visible
- **AND** the complete path remains available

#### Scenario: Non-interactive segments do not look interactive

- **WHEN** a path segment performs no action
- **THEN** it is not styled as an interactive element

### Requirement: The project view switcher is separated by its plane alone

The boundary between the project view switcher and the content below it SHALL be established by
their plane fills alone. A dividing rule MUST NOT be drawn in addition to that plane change.

This applies the shell's existing direction — that a plane boundary must not combine a strong fill
contrast with a strong dividing line — to this specific boundary, where both are currently present.

#### Scenario: No rule under the view switcher

- **WHEN** the project view switcher is displayed above content
- **THEN** no dividing rule is drawn between them
- **AND** their plane fills distinguish them

#### Scenario: The boundary is still legible

- **WHEN** the project view switcher is displayed in either theme
- **THEN** the plane change alone makes the boundary perceptible
