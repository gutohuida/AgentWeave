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
