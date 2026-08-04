## MODIFIED Requirements

### Requirement: Bare invocation is the only entry point

Running `agentweave` with no subcommand SHALL launch or reuse the one local AgentWeave runtime,
open or register the invocation directory as a project through that runtime, and open the app at
that project's overview. This SHALL be the only supported way to begin using AgentWeave.

#### Scenario: First run

- **WHEN** a user runs bare `agentweave` for the first time from a project directory
- **THEN** the system scaffolds local runtime state, runs migrations, launches the native runtime,
  registers that directory, and opens its project overview

#### Scenario: Repeated invocation is idempotent

- **WHEN** a user runs bare `agentweave` from an already registered directory while the runtime is
  running
- **THEN** the system selects that existing project and opens it rather than starting another
  runtime or creating another project

#### Scenario: Invocation from another directory reuses the instance

- **WHEN** a user runs bare `agentweave` from a second directory while the runtime is running
- **THEN** that directory is opened or registered as a second project in the same instance
- **AND** the app opens with the second project selected

#### Scenario: No separate registration ceremony exists

- **WHEN** a user inspects the CLI's available commands
- **THEN** there is no `init`, `activate`, `quick`, or `start` subcommand distinct from bare
  invocation

### Requirement: Status, stop, and reset act on the local instance

`agentweave status` SHALL report whether the local runtime is running, on what port, how many
projects are registered, and which project was opened most recently. `agentweave stop` SHALL stop
the one running instance. `agentweave reset` SHALL destroy local Hub state only after explicit
confirmation and MUST NOT delete registered project directories or source content.

#### Scenario: Status reflects a running multi-project instance

- **WHEN** the runtime is serving more than one project
- **THEN** status reports the port, registered-project count, and most recently opened project

#### Scenario: Stop ends the one instance

- **WHEN** the user runs `agentweave stop`
- **THEN** active runs across projects are terminated through normal shutdown
- **AND** the one runtime process stops

#### Scenario: Reset preserves source directories

- **WHEN** the user confirms `agentweave reset`
- **THEN** local runtime/database state is removed
- **AND** no registered working directory or project source content is deleted
