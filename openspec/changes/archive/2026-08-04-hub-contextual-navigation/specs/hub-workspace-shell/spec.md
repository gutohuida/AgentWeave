## ADDED Requirements

### Requirement: The navigation region carries the navigation of whatever the operator has entered

The workspace SHALL present navigation in one region. When the operator enters an area that has its
own internal navigation, that navigation SHALL be presented in the navigation region rather than
inside the content area, and the navigation region SHALL offer a control that returns to the
project's own navigation in a single action.

The content area MUST NOT render a persistent navigation column of its own.

The navigation region's current mode SHALL be derived from the active destination, so that arriving
by direct link, by browser history, or by an in-application control all produce the same navigation.

#### Scenario: Entering configuration moves its navigation into the rail

- **WHEN** the operator opens a project's configuration
- **THEN** the navigation region lists that area's sections
- **AND** the content area shows only the selected section, with no navigation column beside it

#### Scenario: The containing project is named and reachable

- **WHEN** the navigation region is showing an entered area's sections
- **THEN** the project the area belongs to is identified
- **AND** a single action returns the navigation region to that project's own navigation

#### Scenario: A direct link produces the same navigation as a click

- **WHEN** the operator loads a link addressing a configuration section directly
- **THEN** the navigation region shows that area's sections with the addressed one selected
- **AND** the result is identical to having reached it from within the application

#### Scenario: Project navigation is unchanged by the existence of the mode

- **WHEN** the operator returns from an entered area
- **THEN** the project tree, its agents, and their live state are shown as before
- **AND** no permanent entry has been added for the area that was entered

### Requirement: Project configuration has exactly one affordance, attached to its project

Each project's configuration SHALL be reachable from exactly one visible control, and that control
SHALL be positioned on the row that identifies the project it configures. No second control
anywhere in the workspace SHALL lead to configuration for that same project.

The control MAY be revealed when its project row is hovered or focused rather than being drawn at
rest on every row, provided it remains present for the active project and reachable by keyboard.

#### Scenario: Only one route to configuration exists

- **WHEN** the operator surveys the workspace for a way to configure the active project
- **THEN** exactly one control leads to that project's configuration
- **AND** neither the project header nor the project view strip offers a second route

#### Scenario: The control states its scope by position

- **WHEN** several projects are listed
- **THEN** each project's configuration control is on that project's own row
- **AND** activating it opens configuration for that project

#### Scenario: A revealed control is still reachable without a pointer

- **WHEN** the operator moves keyboard focus through a project row
- **THEN** its configuration control receives focus and can be activated

### Requirement: Agent creation is offered where agents are listed

The control that creates an agent SHALL be presented within the navigation region, at the end of a
project's agent list, in the same manner as the control that adds a project. It MUST NOT also be
presented in the project header.

#### Scenario: The creation control sits with the agents

- **WHEN** the operator expands a project in the navigation region
- **THEN** a create-agent control follows that project's agents
- **AND** activating it opens agent creation scoped to that project

#### Scenario: The header no longer duplicates it

- **WHEN** the project header is displayed
- **THEN** it offers no agent-creation control

## MODIFIED Requirements

### Requirement: Project actions use the shared icon system and readable labels

Open-existing, create-new, create-agent, configure, expand, collapse, and back actions SHALL use the
application's Lucide icon system. They MUST NOT use literal geometric characters, icon-font text,
replacement characters, or mojibake. Every icon-only control SHALL have an accessible name; primary
creation actions SHALL be available as readable text in context.

#### Scenario: Project controls render valid icons

- **WHEN** the operator inspects the project rail
- **THEN** open, create, create-agent, configure, expand, collapse, and back render Lucide icons at
  first paint
- **AND** no corrupted symbol text is present

#### Scenario: Icons remain understandable without sight

- **WHEN** assistive technology inspects an icon-only project control
- **THEN** its accessible name states the action and, where applicable, its current expand/collapse
  state

#### Scenario: No literal character stands in for an icon

- **WHEN** any navigation, header, or conversation control renders a directional or geometric symbol
- **THEN** it is drawn from the icon system rather than typed as a text character
