## ADDED Requirements

### Requirement: The interface presents related navigation and content planes

Top-level navigation and content SHALL use the approved mock's distinct but related indigo and ink
planes. Their boundary SHALL remain subtle and MUST NOT combine a strong fill contrast with a
strong dividing line.

Surfaces that carry a distinct fill SHALL be limited to those that genuinely sit above the ground
plane — menus, popovers, dialogs, the composer, and self-contained content surfaces.

#### Scenario: Navigation remains related to content

- **WHEN** navigation and content are displayed side by side
- **THEN** their related fills distinguish their roles
- **AND** neither reads as a detached panel inset into the other

#### Scenario: Lifted surfaces are distinguishable

- **WHEN** a menu, popover, dialog, or content surface is displayed
- **THEN** it is distinguishable from the ground plane by its own fill, outline, or shadow

### Requirement: Two adjacent regions are separated by one signal, not two

Where a boundary between regions must be perceptible, the interface SHALL express it with a single
signal — either a contrast in fill or a dividing line, not both. A boundary expressed by two
simultaneous signals reads as heavier than intended and is not permitted.

#### Scenario: A boundary uses a single signal

- **WHEN** two adjacent regions are separated
- **THEN** either their fills differ or a dividing line is drawn, but not both

#### Scenario: The dividing line is subordinate to content

- **WHEN** a dividing line is drawn
- **THEN** it is less prominent than the outlines of interactive controls in either region

### Requirement: Primary panes are resizable and the choice is remembered

The operator SHALL be able to resize the primary panes by dragging their boundary. The chosen size
SHALL persist across sessions, and SHALL be restorable to its default without manual measurement.

The drag affordance SHALL present a target larger than the visible boundary, and SHALL indicate
that it is draggable on hover and while dragging.

#### Scenario: The boundary is draggable and forgiving

- **WHEN** the operator moves the pointer near the boundary between panes
- **THEN** a drag affordance is available before the pointer reaches the visible line
- **AND** the boundary indicates that it can be dragged

#### Scenario: Sizes are clamped to usable bounds

- **WHEN** the operator drags a pane beyond a usable size
- **THEN** the pane stops at its minimum or maximum rather than becoming unusable

#### Scenario: The size persists and can be reset

- **WHEN** the operator resizes a pane and later returns to the application
- **THEN** the chosen size is restored
- **AND** a single gesture returns the pane to its default size

### Requirement: Scrollbars are unobtrusive

Scrollbars SHALL be presented as an overlay indicator rather than as a filled channel. They MUST
NOT render a track background or stepper buttons, and their handle SHALL be inset from the content
edge and become more prominent on hover.

#### Scenario: A scrollbar shows only its handle

- **WHEN** a scrollable region is displayed
- **THEN** only a rounded handle is visible, inset from the edge
- **AND** no track background or stepper button is drawn

#### Scenario: The handle strengthens on hover

- **WHEN** the operator hovers the scrollbar
- **THEN** the handle becomes more prominent

### Requirement: Navigation lists live entities; project views are reached in the content area

The navigation region SHALL list entities that have their own live state — projects and their
agents. Views scoped to a project, such as its tasks, specs, jobs, activity, and environment,
SHALL be reached within the content area rather than by adding entries to the navigation region.

Adding a further project-scoped view MUST NOT require adding a navigation entry.

#### Scenario: Navigation shows live entities with their state

- **WHEN** the navigation region is displayed
- **THEN** it lists projects and their agents
- **AND** each agent shows its current state

#### Scenario: A project's views are reached from the project

- **WHEN** the operator opens a project
- **THEN** its tasks, specs, jobs, activity, and environment are reachable within the content area

#### Scenario: A project row both navigates and expands

- **WHEN** the operator activates a project's name
- **THEN** that project opens in the content area
- **WHEN** the operator activates that project's expander
- **THEN** its agents are revealed or hidden without leaving the current view

#### Scenario: Adding a view does not crowd navigation

- **WHEN** a further project-scoped view is introduced
- **THEN** it appears among the project's views
- **AND** the navigation region gains no entry

#### Scenario: Returning to the project from an agent

- **WHEN** the operator is viewing an agent's conversation
- **THEN** the containing project is identified and directly reachable

### Requirement: An agent's identity colour is applied consistently wherever it appears

An agent's assigned colour SHALL identify that agent in every surface that represents it —
navigation, conversation entries, task assignment, and activity — so the same colour always means
the same agent.

#### Scenario: One agent, one colour, everywhere

- **WHEN** an agent appears in navigation, in a conversation entry, and as a task's assignee
- **THEN** the same colour identifies it in each place

#### Scenario: Colour never stands alone

- **WHEN** an agent's colour is used to identify it
- **THEN** its name is also present in text
