## ADDED Requirements

### Requirement: Navigation reads from the registered project collection

Navigation SHALL read its project and agent tree from one adapter containing every registered
project the local operator can reach. The operator SHALL be able to open an existing project
directory, explicitly create a new one, and switch projects without changing credentials.

The adapter SHALL preserve project and agent live state for inactive projects. Project switching
MUST NOT leak conversations, drafts, cached server state, or in-flight mutation results across
project identifiers.

#### Scenario: Multiple projects are rendered from the collection

- **WHEN** the local instance has two registered projects
- **THEN** the adapter returns both projects with their agents
- **AND** the unchanged collection rail renders both

#### Scenario: Project management is offered

- **WHEN** the operator inspects the project collection controls
- **THEN** distinct actions to open an existing directory and create a new directory are available

#### Scenario: Switching preserves isolation

- **WHEN** the operator switches projects while a request or agent run remains active in the first
  project
- **THEN** the first project's state continues under its identity
- **AND** none of it is rendered as belonging to the selected project

### Requirement: Conversation navigation is URL-backed and project-scoped

Normal project, agent, and conversation navigation SHALL be represented in the browser URL using
stable project and AgentWeave conversation identity. Reload and back/forward navigation SHALL
restore the represented destination. Provider session identifiers MUST NOT be used as URL identity.

#### Scenario: A conversation URL reloads

- **WHEN** the operator reloads an agent conversation in one project
- **THEN** the same project, agent, and AgentWeave conversation are restored

#### Scenario: Browser history crosses projects

- **WHEN** the operator visits project A, then project B, then activates Back
- **THEN** project A and its prior destination are restored without changing credentials

## REMOVED Requirements

### Requirement: Navigation reads from a project collection populated with one project

**Reason**: The local Hub now owns a collection of registered projects and the operator can open,
create, and switch between them. The one-authenticated-project adapter and its prohibition on
project management no longer describe the implemented product.

**Migration**: Replaced by "Navigation reads from the registered project collection" above. The
rail keeps the collection-shaped adapter while its source, controls, and isolation guarantees
become explicitly multi-project.
