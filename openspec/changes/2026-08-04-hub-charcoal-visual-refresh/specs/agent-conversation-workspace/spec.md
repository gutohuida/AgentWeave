## ADDED Requirements

### Requirement: Composed text begins at the composer's leading edge

The composer SHALL present its text area on its own row, occupying the full width of the composer
surface. No control SHALL precede the text area on that row.

Controls belonging to the composer SHALL occupy a control row beneath the text area.

#### Scenario: Text starts at the leading edge

- **WHEN** the operator focuses the composer and types
- **THEN** the text begins at the composer surface's leading edge, inset only by the surface's own
  padding

#### Scenario: The text area keeps the full measure at a narrow viewport

- **WHEN** the conversation is displayed at a narrow viewport
- **THEN** the text area's width is the composer surface's width less its padding
- **AND** no control reduces the width available to text

#### Scenario: Controls are reachable beneath the text

- **WHEN** the composer is displayed
- **THEN** the agent target control and the send control are presented in a row beneath the text
  area

### Requirement: The composer control row is an extensible pair of slots

The composer's control row SHALL be composed of a leading slot and a trailing slot. The trailing
slot SHALL hold the send control. The leading slot SHALL hold target and per-turn controls.

Adding a control to either slot MUST NOT require changing the composer's layout.

#### Scenario: Controls are added without relayout

- **WHEN** a further per-turn control is added to the leading slot
- **THEN** the composer's text area, autogrow behaviour, and send control are unchanged

#### Scenario: Existing composer behaviour survives the layout change

- **WHEN** the composer is presented as a column
- **THEN** draft persistence, autogrow within bounds, the trigger menu, submission on Enter, and
  input while the agent is running all behave as previously specified
