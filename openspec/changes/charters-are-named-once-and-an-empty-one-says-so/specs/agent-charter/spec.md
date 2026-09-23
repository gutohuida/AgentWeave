## ADDED Requirements

### Requirement: A charter's content states something

The Hub SHALL refuse to create a charter, or to update one, with content that contains no visible character, and an agent bound to a charter whose content is nonetheless empty SHALL be told plainly that the charter is empty.

A charter is delivered to its agent on every turn under a heading that names it. A heading followed
by nothing reads as a contract that was cut off, and the agent cannot tell that from a delivery
failure. The context response SHALL also report the empty content as missing, so that an empty
charter is not reported as a fully configured agent.

#### Scenario: Creating a charter with blank content is refused

- **WHEN** an operator creates a charter whose content is empty or only whitespace
- **THEN** the request is refused, naming the content field
- **AND** no charter is created

#### Scenario: Blanking an existing charter is refused

- **WHEN** an operator updates a charter's content to empty or only whitespace
- **THEN** the request is refused, naming the content field
- **AND** the charter's content is unchanged

#### Scenario: An empty charter that exists anyway is described as empty

- **WHEN** an agent is bound to a charter whose stored content is empty
- **THEN** the agent's context names the charter and states that it is empty
- **AND** the context response reports the charter's content as missing

### Requirement: A charter's name is unique within its project

The Hub SHALL refuse to create or rename a charter to a name another charter in the same project already has, and SHALL say which name is taken.

Where a charter is chosen, it is chosen by its name. Two charters with one name cannot be told apart
at the moment an operator binds one, and nothing in the Hub resolves a charter by name to rescue the
choice afterwards.

Charters that already share a name when this rule arrives SHALL be kept, not deleted: the oldest
keeps the name and each later one is given a distinguishing suffix, so that every agent stays bound
to the charter it was bound to.

#### Scenario: Creating a charter under a taken name is refused

- **WHEN** an operator creates a charter with a name another charter in the project already has
- **THEN** the request is refused, naming the taken name
- **AND** no charter is created

#### Scenario: Renaming a charter to a taken name is refused

- **WHEN** an operator renames a charter to a name another charter in the project already has
- **THEN** the request is refused, naming the taken name
- **AND** the charter keeps its name

#### Scenario: The same name in two projects is allowed

- **WHEN** two projects each have a charter with the same name
- **THEN** both charters exist

#### Scenario: Existing duplicates are renamed, not removed

- **WHEN** a project already holds several charters with one name as this rule takes effect
- **THEN** the oldest keeps the name and each later one carries a distinguishing suffix
- **AND** every agent is still bound to the same charter as before
