## MODIFIED Requirements

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

## ADDED Requirements

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
