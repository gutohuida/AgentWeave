# hub-workspace-shell Specification

## Purpose
Define the Hub workspace shell's visual hierarchy, related navigation/content planes, lifted
surfaces, and accessible project actions against the approved full design mock.
## Requirements
### Requirement: The running workspace shell follows the approved full design mock

The Hub SHALL use `openspec/changes/2026-07-30-hub-native-experience/mock-full.html` as the primary
visual reference for its reachable workspace shell. The running application SHALL preserve the
mock's indigo project rail, ink content plane, project header hierarchy, compact project tabs,
bounded content width, restrained summary surfaces, typography, density, radii, and interaction
states while rendering current live behavior and data.

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

#### Scenario: Inspiration does not become copied branding

- **WHEN** T3-inspired interaction patterns are applied
- **THEN** no T3 logo, brand color, product copy, account surface, or chat-specific navigation is
  reproduced

### Requirement: Navigation and content use distinct but related planes

The desktop project rail SHALL use the approved mock's indigo navigation plane and content SHALL
use its related ink ground. Their boundary SHALL remain subtle and MUST NOT combine a strong fill
contrast with a strong dividing line.

This requirement supersedes the older umbrella direction that required navigation and content to
use an identical fill; explicit mock alignment requires the two related planes.

#### Scenario: The rail is identifiable without reading as a detached panel

- **WHEN** navigation and content are displayed side by side
- **THEN** their related indigo/ink fills distinguish their roles
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

Open-existing, create-new, expand, and collapse actions SHALL use the application's Lucide icon
system. They MUST NOT use literal geometric characters, icon-font text, replacement characters, or
mojibake. Every icon-only control SHALL have an accessible name; primary creation actions SHALL be
available as readable text in context.

#### Scenario: Project controls render valid icons

- **WHEN** the operator inspects the project rail
- **THEN** open, create, expand, and collapse render Lucide icons at first paint
- **AND** no corrupted symbol text is present

#### Scenario: Icons remain understandable without sight

- **WHEN** assistive technology inspects an icon-only project control
- **THEN** its accessible name states the action and current expand/collapse state

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

