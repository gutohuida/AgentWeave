# task-lifecycle-governance

## ADDED Requirements

### Requirement: A task's requirement links are visible where the operator manages the task

The interface presenting a task to the operator SHALL show which specification requirements, if any,
the task is linked to, without requiring the operator to open the task's full detail first.

Where a linked requirement's only current evidence was rejected, that MUST be visually distinguished
from a link to a requirement with no such rejection, so a task that looks approvable does not hide a
refused claim inside it.

#### Scenario: A task's linked requirements are visible on the board

- **WHEN** a task linked to one or more specification requirements is shown on the task board
- **THEN** the identifiers of its linked requirements are visible without expanding the task

#### Scenario: A rejected requirement's link is visually distinct

- **WHEN** a task is linked to a requirement whose only current evidence was rejected
- **THEN** that link is shown with a treatment distinct from a link carrying no such rejection

### Requirement: A task's full detail opens in a view sized to hold it

The interface SHALL present a task's full detail — description, acceptance criteria, deliverables,
notes, and requirement links — in a view sized independently of the task board's column layout, not
constrained to the width of a board column.

#### Scenario: A task with substantial detail is fully readable when opened

- **WHEN** the operator opens a task carrying a long description, multiple acceptance criteria, and
  requirement links
- **THEN** every one of those is rendered without being clipped or requiring the board column's own
  width

### Requirement: Navigating from a task's requirement link reaches that requirement in its document

Following a task's link to one of its requirements SHALL open the specification document that
declares it, scrolled to that requirement, not merely to the top of the document.

#### Scenario: Following a requirement link reaches the requirement itself

- **WHEN** the operator follows a task's link to a specific requirement
- **THEN** the specification document opens with that requirement in view
