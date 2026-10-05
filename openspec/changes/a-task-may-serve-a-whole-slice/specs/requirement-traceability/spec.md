## ADDED Requirements

### Requirement: A task card shows where each requirement it serves stands

The task card SHALL show, for each requirement the task serves, that requirement's coverage state as computed for the document, and when the task serves more than four requirements it SHALL also show a count of those requirements by state.

A task may now serve a whole slice's requirements. A card that shows only their identifiers reads
as one unit of work, and a rejected requirement inside it is what the FR-11 incident hid. The state
is the one the coverage computation gives, so the card cannot disagree with the document view. The
count keeps a card serving many requirements readable without hiding any of them.

#### Scenario: Each chip carries its requirement's state

- **WHEN** a task serving one verified, one awaiting-review and one rejected requirement is shown
  on the board
- **THEN** each requirement's chip is marked with its own state, and the rejected one is marked as
  rejected

#### Scenario: A card serving many requirements counts them by state

- **WHEN** a task serving five requirements, three verified and two not yet evidenced, is shown on
  the board
- **THEN** the card shows all five chips and a count naming three verified and two open

#### Scenario: A card serving few requirements shows no count

- **WHEN** a task serving four requirements or fewer is shown on the board
- **THEN** the card shows their chips and no count
