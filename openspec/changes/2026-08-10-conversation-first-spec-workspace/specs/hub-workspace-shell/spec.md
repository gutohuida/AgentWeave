## ADDED Requirements

### Requirement: Navigation collapses only when the operator asks, and stays navigable when it does

The navigation rail SHALL NOT change its collapsed state on its own. No destination, page, or layout
may collapse it on the operator's behalf.

While collapsed, the rail SHALL remain navigable: every project and agent reachable from the
expanded rail SHALL be reachable from the collapsed one, each with an accessible name, with the
active one indicated and the expand control reachable.

The collapsed state SHALL persist across reloads.

A rail that renders no destinations is not collapsed, it is hidden, and hiding navigation is not a
layout decision the application makes for the operator. This was reached by a page needing
horizontal space and taking it from navigation — which left the rail showing an avatar and nothing
else, with no way to expand it and no way back.

#### Scenario: Opening a page that wants the space

- **WHEN** the operator opens any destination
- **THEN** the rail's collapsed state is whatever the operator last set
- **AND** no destination changes it

#### Scenario: Navigating from the collapsed rail

- **WHEN** the rail is collapsed
- **THEN** every project and agent available when expanded is available and named
- **AND** the active one is indicated
- **AND** the rail can be expanded again from within it

#### Scenario: The choice is remembered

- **WHEN** the operator collapses the rail and reloads
- **THEN** the rail is still collapsed
