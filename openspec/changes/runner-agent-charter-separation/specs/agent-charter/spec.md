## ADDED Requirements

### Requirement: Charters are project-scoped, authored Hub records

The Hub SHALL persist charters as project-scoped database rows, each with a name and markdown
behavior content. A charter SHALL NOT be represented as a file on disk or as a fixed, hardcoded
list of personas.

#### Scenario: Charter is created

- **WHEN** an operator creates a charter with a name and content
- **THEN** the Hub persists it as a project-scoped record with a stable identifier

#### Scenario: Charter content is edited

- **WHEN** an operator edits an existing charter's content and saves
- **THEN** subsequent context lookups for agents bound to that charter return the updated content

### Requirement: Existing role guides seed initial charters once

A project with zero charter records SHALL be seeded, on first Hub start after this change ships,
with one charter per previously-bundled role guide, using the guide's label as the charter name and
its markdown body as the charter content. This seeding SHALL run at most once per project.

#### Scenario: First boot seeds charters from bundled role guides

- **WHEN** a project has no charter records and the Hub starts for the first time after this change
- **THEN** the Hub creates one charter per previously-bundled role guide with matching name and
  content

#### Scenario: Seeding does not repeat

- **WHEN** the Hub restarts after charters already exist for a project
- **THEN** no additional seed charters are created

### Requirement: An agent is bound to at most one charter

Each Hub `Agent` record SHALL reference at most one charter record. An agent with no bound charter
SHALL remain usable — its context response SHALL state plainly that no charter is assigned rather
than erroring or fabricating behavior content.

#### Scenario: Agent context resolves its bound charter

- **WHEN** an agent with a bound charter begins a turn
- **THEN** the supplied context includes that charter's content

#### Scenario: Agent has no bound charter

- **WHEN** an agent with no bound charter requests its context
- **THEN** the response includes project instructions and a clear no-charter notice, and does not
  error

### Requirement: Charter management is available through the Hub UI

The Hub UI SHALL provide a screen to list, create, edit, and delete charters, and to bind an agent
to a charter from the agent's detail view. This screen replaces any prior role-assignment command
or interface.

#### Scenario: Operator authors a new charter

- **WHEN** an operator opens the charter screen and creates a charter with custom content
- **THEN** the charter is available to bind to any agent in the project

#### Scenario: Operator reassigns an agent's charter

- **WHEN** an operator selects a different charter for an agent in the Hub UI
- **THEN** the agent's charter binding updates and its next context response reflects the new
  charter
