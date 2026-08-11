## MODIFIED Requirements

### Requirement: Charter management is available through the Hub UI

The Hub UI SHALL provide a screen to list, read, create, edit, and delete charters, and to bind an
agent to a charter from the agent's detail view. This screen replaces any prior role-assignment
command or interface.

Reading a charter's full content SHALL be possible without opening any surface that can modify it. A
charter's content is the text injected into an agent's turn, so an operator choosing which charter to
bind SHALL be able to see all of it.

The screen SHALL allow more than one charter to be open for reading at the same time, so that two can
be compared without closing either.

#### Scenario: Operator reads a charter without opening the editor

- **WHEN** an operator expands a charter on the charter screen
- **THEN** its full content is shown, and no editable field, save action, or discard action is
  presented

#### Scenario: Two charters are compared

- **WHEN** an operator opens one charter for reading and then opens a second
- **THEN** both remain open, and the first is not closed by the second

#### Scenario: The list is legible when nothing is expanded

- **WHEN** the charter screen is first opened
- **THEN** every charter is collapsed to a short summary, and the list of charter names is readable
  without scrolling past full documents

#### Scenario: Operator authors a new charter

- **WHEN** an operator opens the charter screen and creates a charter with custom content
- **THEN** the charter is available to bind to any agent in the project

#### Scenario: Operator reassigns an agent's charter

- **WHEN** an operator selects a different charter for an agent in the Hub UI
- **THEN** the agent's charter binding updates and its next context response reflects the new
  charter
