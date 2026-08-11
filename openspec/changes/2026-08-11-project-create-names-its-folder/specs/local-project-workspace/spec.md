## MODIFIED Requirements

### Requirement: Project creation and opening are explicit and bounded

The operator SHALL be able to open an existing directory or explicitly create and register one new
directory. Opening MUST NOT create the target directory. Creating MUST create exactly the requested
new directory and MUST refuse an existing non-empty target.

Creation SHALL be expressed as an existing parent directory plus a name for the new project. The
created directory SHALL be that name within that parent, and the project SHALL take that same name.
The operator SHALL NOT be required to compose a filesystem path in order to create a project.

The parent directory MUST already exist. Creation SHALL NOT create intermediate directories.

A project name offered at creation MUST be a single path segment. A name that is empty, that contains
a path separator, that is a traversal segment, or that the host filesystem rejects SHALL be refused
with a message naming the problem, and MUST NOT be silently rewritten into an acceptable one.

Before the operator confirms, the interface SHALL show the absolute path that will be created,
derived from the same values that are submitted.

Registration SHALL atomically create the project, seed its default runners and starter charters,
and write its identity marker. It SHALL NOT initialize git, start an agent, create a specification,
or otherwise modify project source.

#### Scenario: An existing directory is opened

- **WHEN** the operator chooses Open and supplies an available unregistered directory
- **THEN** it is registered without changing its source content beyond AgentWeave runtime metadata
- **AND** it becomes the selected project

#### Scenario: A new directory is created from a parent and a name

- **WHEN** the operator chooses Create, supplies an existing parent directory and the name `my-app`
- **THEN** exactly `my-app` is created within that parent and registered
- **AND** the project is named `my-app`

#### Scenario: The target is shown before it is created

- **WHEN** the operator has supplied a parent and a name
- **THEN** the absolute path that will be created is displayed before confirmation

#### Scenario: A name that is not a directory name is refused

- **WHEN** the operator supplies a project name containing a path separator or a traversal segment
- **THEN** creation is refused with a message naming the problem
- **AND** no directory is created, and the name is not rewritten into an acceptable one

#### Scenario: Marker creation fails

- **WHEN** the identity marker cannot be written during a new registration
- **THEN** the project transaction is rolled back or reported as incomplete with a repair action
- **AND** no silently unusable project is presented as ready

### Requirement: The operator can browse for a project directory

The Hub UI SHALL let the operator browse the filesystem visible to the Hub process to choose a
project directory, rather than requiring an absolute path to be typed from memory.

What browsing returns SHALL be directly usable in the mode it was invoked from, without the operator
editing it. Because browsing yields a directory that exists, in create mode it SHALL supply the
parent directory rather than the project directory itself.

#### Scenario: Browsing supplies a usable value in create mode

- **WHEN** the operator browses for a directory while creating a project
- **THEN** the chosen directory becomes the parent, and the operator supplies only a name
- **AND** the operator is not required to edit the chosen path

#### Scenario: Browsing supplies a usable value in open mode

- **WHEN** the operator browses for a directory while opening a project
- **THEN** the chosen directory is the project directory, and no further editing is required
