## MODIFIED Requirements

### Requirement: Projects have stable directory-backed identity

Each project SHALL have a stable project identifier and one canonical absolute working directory.
The identifier SHALL survive project rename and explicit directory relocation. The system MUST
reject two active project records resolving to the same canonical directory.

A registered directory SHALL contain a versioned, non-secret AgentWeave project marker carrying its
stable project identifier. The marker MUST NOT contain credentials, settings, or an absolute path.

A directory whose marker names a project identifier that the opening database holds no record of,
and which is not already bound to any other project in that database, SHALL be adopted under the
marker's own identifier rather than refused. Adoption seeds the project the same way a newly
created project is seeded (default runners, starter charters) and records that the project was
adopted rather than newly created.

#### Scenario: The same directory is opened twice

- **WHEN** an operator opens a directory already registered through an equivalent path
- **THEN** the existing project is selected
- **AND** no duplicate project is created

#### Scenario: A project directory is relocated

- **WHEN** an unavailable project's marked directory is opened at a new path and it has no active
  run or worktree mutation
- **THEN** the existing project is rebound to the new canonical directory
- **AND** every task, conversation, run, agent, and setting retains the same project identifier

#### Scenario: A marker was copied

- **WHEN** a marked directory and the existing registered directory are both available, and the
  opening database already holds a project record for the marker's identifier
- **THEN** the copy is reported as an identity conflict
- **AND** it is not merged or adopted without an explicit register-copy-as-new action

#### Scenario: A directory carries an identifier this database has never registered

- **WHEN** a directory's marker names a project identifier absent from the opening database, and
  no project in that database is already bound to this directory's path
- **THEN** the directory is opened as that project, under the marker's own identifier
- **AND** the project is seeded with default runners and starter charters as a new project would be
- **AND** the adoption is recorded so it is distinguishable after the fact from ordinary creation

#### Scenario: A project is deleted and its directory is reopened

- **WHEN** a project is deleted and the same directory, still carrying its original marker, is
  opened again
- **THEN** the directory is adopted under its original identifier rather than refused
