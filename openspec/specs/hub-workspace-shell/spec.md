# hub-workspace-shell Specification

## Purpose
Define the Hub workspace shell's visual hierarchy, related navigation/content planes, lifted
surfaces, and accessible project actions against the approved full design mock.
## Requirements
### Requirement: The running workspace shell follows the approved full design mock

The Hub SHALL use `openspec/changes/2026-07-30-hub-native-experience/mock-full.html` as the primary
visual reference for its reachable workspace shell. The running application SHALL preserve the
mock's project header hierarchy, compact project tabs, bounded content width, restrained summary
surfaces, typography, density, radii, and interaction states while rendering current live behavior
and data.

The mock's *palette* is explicitly superseded. Where the mock specifies an indigo project rail and
an ink content plane, the running application SHALL instead use the neutral graphite ramp defined
below. The mock remains authoritative for hierarchy, density, and interaction; it is no longer
authoritative for hue.

T3-inspired interaction qualities MAY inform restraint, translucency, rounded controls, and press
feedback, but AgentWeave MUST retain its own palette, branding, navigation, and product identity.

#### Scenario: The desktop shell matches the reference hierarchy

- **WHEN** a project is open at a desktop viewport
- **THEN** the project rail, project header/actions, project tabs, and content hierarchy correspond
  to the reachable project shell in the full design mock
- **AND** a permanent global dashboard strip does not compete with that hierarchy

#### Scenario: Current behavior survives visual alignment

- **WHEN** the shell is aligned to the mock
- **THEN** multi-project selection, URL-backed tabs and conversations, live state, rail resizing,
  and narrow-width access continue to work

#### Scenario: The mock's hue is not reproduced

- **WHEN** the running shell is compared against the mock
- **THEN** hierarchy, density, and interaction correspond to the mock
- **AND** the rail and content planes use the neutral graphite ramp rather than the mock's indigo
  and ink fills

#### Scenario: Inspiration does not become copied branding

- **WHEN** T3-inspired interaction patterns are applied
- **THEN** no T3 logo, brand color, product copy, account surface, or chat-specific navigation is
  reproduced

### Requirement: Navigation and content use distinct but related planes

The desktop project rail and the content ground SHALL be drawn from the same neutral graphite ramp
at adjacent steps, so their roles are distinguishable by luminance alone. Their boundary SHALL
remain subtle and MUST NOT combine a strong fill contrast with a strong dividing line.

This requirement supersedes both the older umbrella direction that required navigation and content
to use an identical fill, and the subsequent direction that required the mock's indigo and ink
fills.

#### Scenario: The rail is identifiable without reading as a detached panel

- **WHEN** navigation and content are displayed side by side
- **THEN** their adjacent neutral fills distinguish their roles by luminance
- **AND** the boundary remains less prominent than an interactive control outline

### Requirement: Lifted surfaces are opaque and token-defined

Every menu, popover, dialog, composer, and other lifted surface SHALL resolve its background from a
defined semantic token in both light and dark themes. A modal dialog SHALL render an opaque panel
over a separate scrim and MUST NOT expose the underlying page through an undefined or transparent
panel fill.

#### Scenario: Project management opens an opaque dialog

- **WHEN** the operator opens either project-management action in either theme
- **THEN** the dialog panel has a defined opaque surface fill
- **AND** the underlying workspace is visible only through the surrounding scrim

#### Scenario: Undefined tokens fail verification

- **WHEN** the production stylesheet and touched components are checked
- **THEN** every referenced semantic surface token is defined for light and dark modes

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

### Requirement: The chrome is neutral and hue is reserved for meaning

Every background, surface, and border token of the application chrome SHALL be neutral or
near-neutral in both modes. The chrome MUST NOT carry a perceptible hue cast.

Hue in the interface SHALL be reserved for elements that carry meaning: the agent identity palette,
the semantic status colours, and the single state accent defined below. A component MUST NOT
introduce a colour literal outside the token system.

#### Scenario: Chrome reads as neutral

- **WHEN** the workspace is displayed in either mode
- **THEN** the ground plane, rail, elevated surfaces, and borders read as neutral greys

#### Scenario: Meaningful colour survives the neutral chrome

- **WHEN** agents, statuses, and budget conditions are displayed against the neutral chrome
- **THEN** agent identity colours and semantic status colours remain distinguishable from the chrome
  and from each other

#### Scenario: Colour literals do not bypass the token system

- **WHEN** the application's components are checked for colour values
- **THEN** no component declares a raw hex or `rgba()` colour in place of a semantic token

### Requirement: The text ramp keeps three levels and every level clears a stated contrast bar

The neutral text ramp SHALL provide three visually distinguishable levels in both modes, and every
level SHALL reach a contrast ratio of at least **3.0** against every surface it can be set on — the
ground plane and all three elevated surfaces.

The two primary levels SHALL additionally reach **AA 4.5** for normal text. The 3.0 bar applies to
the third level only, and to the semantic status hues.

3.0 rather than AA 4.5 for the third level is a deliberate, recorded exemption. Raising it to 4.5
brings it within one perceptual step of the second level, collapsing the three-level ramp into two;
the ramp carries the distinction between primary content, secondary content, and incidental
metadata, so preserving it is preferred to a uniform bar. The exemption SHALL NOT be widened beyond
the third level and the status hues.

This bar SHALL be enforced by an automated check against the stylesheet, not merely documented, so
that a later palette change that falls below it fails rather than ships.

#### Scenario: Every text level is legible on every surface

- **WHEN** any neutral text level is rendered on the ground plane or any elevated surface, in either
  mode
- **THEN** its contrast ratio against that surface is at least 3.0

#### Scenario: The exemption stays narrow

- **WHEN** the primary and secondary text levels are measured against every surface in either mode
- **THEN** each reaches at least 4.5

#### Scenario: The three levels remain distinguishable

- **WHEN** the ramp is measured level against level
- **THEN** each level is perceptibly separated from the one above it, and the levels recede in order
  from the ground plane

#### Scenario: Status hues are legible on every surface

- **WHEN** a semantic status colour is rendered on any surface in either mode
- **THEN** its contrast ratio against that surface is at least 3.0

#### Scenario: A regression below the bar fails the build

- **WHEN** a palette token is changed so that any level falls below its stated bar
- **THEN** the automated contrast check fails and identifies the token, the surface, and the ratio

### Requirement: Emphasis is monochrome and the accent marks state only

The primary control fill SHALL be monochrome — near-white against the dark ground and near-black
against the light ground.

Exactly one accent hue SHALL be defined per mode. It SHALL be used only to express state: the focus
ring, the marker identifying an active navigation row, and selection. The accent MUST NOT be used
as the fill of any control.

#### Scenario: Primary controls are monochrome

- **WHEN** a primary control is displayed in either mode
- **THEN** its fill is monochrome and its label meets contrast against that fill

#### Scenario: The accent appears only as state

- **WHEN** the application's controls are displayed at rest
- **THEN** the accent hue appears only as a focus ring, an active-row marker, or a selection
  indication, and never as a control's fill

### Requirement: The active navigation row is marked without a resting fill

A navigation row identifying the currently open destination SHALL NOT carry a background fill at
rest. It SHALL be identified by a leading accent marker together with a stronger label treatment.

Background fill in navigation rows SHALL express pointer and press state only. The marker SHALL
occupy layout for every row whether or not it is visible, so gaining or losing it displaces no
content.

The row's programmatic active state SHALL be unchanged: the element continues to expose
`aria-current` and its active data attribute regardless of how the state is drawn.

#### Scenario: The open project carries no fill at rest

- **WHEN** a project is open and the pointer is elsewhere
- **THEN** that project's rail row shows a leading marker and a stronger label
- **AND** the row carries no background fill

#### Scenario: Hover fill still applies to the active row

- **WHEN** the operator hovers the row of the currently open project
- **THEN** the row gains the hover fill
- **AND** the leading marker remains

#### Scenario: Gaining the marker displaces nothing

- **WHEN** the operator opens a different project
- **THEN** the marker moves between rows without shifting any row's label position

#### Scenario: Assistive technology still reports the active row

- **WHEN** the rail is inspected programmatically
- **THEN** the row of the currently open project reports its active state

### Requirement: The project header is not a box

The project header SHALL sit on the ground plane. It MUST NOT carry a fill distinct from the ground
plane and MUST NOT be closed by a dividing rule.

#### Scenario: No band encloses the project header

- **WHEN** a project is open
- **THEN** the project header carries no distinct fill and no rule beneath it

### Requirement: A project's directory is presented as readable segments

The project header SHALL present the project's working directory as path segments rather than as a
single interpolated string. When the directory is too long for the available width, it SHALL be
elided from the middle so that the leading root and the final segments both remain visible.

The complete path SHALL remain available to the operator without navigating away.

#### Scenario: A long path keeps its identifying tail

- **WHEN** a project's directory is too long to display in full
- **THEN** the path is elided from the middle
- **AND** the final segments remain visible

#### Scenario: The full path stays reachable

- **WHEN** the displayed directory is elided
- **THEN** the operator can obtain the complete path from the header itself

### Requirement: The application offers light and dark modes only

The application SHALL expose exactly two appearance choices: light and dark. It MUST NOT present a
theme, palette, or accent selector that does not change the rendered application.

#### Scenario: No inert appearance control is presented

- **WHEN** the operator opens application setup
- **THEN** the only appearance choice offered is light or dark
- **AND** every appearance control presented changes the rendered application

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

### Requirement: A command palette reaches conversations, agents, documents, and tasks without navigating the tree

The Hub SHALL offer a keyboard-activated command palette that searches, within the current project,
its conversations, agents, spec documents, and tasks, and navigates to the selected result on
activation.

The palette SHALL be reachable by a fixed keyboard shortcut from anywhere in the Hub, and SHALL NOT
open while the operator's focus is in a text input or the composer and the triggering key is typed
without its required modifier.

Dismissing the palette without a selection MUST NOT navigate anywhere or otherwise change what is
displayed.

#### Scenario: The palette opens on its shortcut

- **WHEN** the operator activates the palette's keyboard shortcut from anywhere in the Hub
- **THEN** a searchable overlay opens listing conversations, agents, spec documents, and tasks from
  the current project

#### Scenario: Typing in a text field does not open the palette

- **WHEN** the operator's focus is in a text input or the composer and they type the palette's
  trigger key without its modifier
- **THEN** the palette does not open
- **AND** the typed character reaches the focused field

#### Scenario: Selecting a result navigates to it

- **WHEN** the operator selects a conversation, agent, spec document, or task from the palette
- **THEN** the Hub navigates to that destination
- **AND** the palette closes

#### Scenario: Dismissing without selecting changes nothing

- **WHEN** the operator dismisses the palette without selecting a result
- **THEN** the Hub's displayed destination is unchanged

