## ADDED Requirements

### Requirement: Bare invocation is the only entry point

Running `agentweave` with no subcommand SHALL launch the Hub-owned runtime in app mode. This SHALL
be the only supported way to begin using AgentWeave.

Directory-to-project registration is out of scope for this requirement — today there is exactly one
project, bootstrapped on first native start, independent of invocation directory. Per-directory
project registration is deferred to the "Local multi-project workspace" slice; when it lands, it
changes what "the project" means for this entry point, not the entry point itself.

#### Scenario: First run

- **WHEN** a user runs bare `agentweave` for the first time
- **THEN** the system scaffolds local Hub state, runs migrations, and launches the native Hub
  runtime in app mode

#### Scenario: Repeated invocation is idempotent

- **WHEN** a user runs bare `agentweave` while the Hub is already running
- **THEN** the system opens the app window against the running instance rather than starting a
  second instance

#### Scenario: No separate registration ceremony exists

- **WHEN** a user inspects the CLI's available commands
- **THEN** there is no `init`, `activate`, `quick`, or `start` subcommand distinct from bare
  invocation

### Requirement: Environment readiness is diagnosable without starting the app

`agentweave doctor` SHALL report environment readiness — Python version, runner CLIs on PATH,
port availability, database accessibility, and file permissions — without requiring the Hub to be
running.

#### Scenario: Doctor runs before first launch

- **WHEN** a user runs `agentweave doctor` in a directory that has never been registered
- **THEN** the system reports readiness checks without creating a project or starting the Hub

#### Scenario: Doctor explains a failed install

- **WHEN** a required dependency, port, or permission check fails
- **THEN** the reported check names the failure and a remediation hint

### Requirement: Status, stop, and reset act on the local instance

`agentweave status` SHALL report whether the Hub-owned runtime is running, on what port, and
against which project. `agentweave stop` SHALL stop a running instance. `agentweave reset` SHALL
destroy local Hub state as a recovery path when the instance is wedged.

#### Scenario: Status reflects a running instance

- **WHEN** the Hub is running for a project
- **THEN** `agentweave status` reports it as running, its port, and the project it serves

#### Scenario: Status reflects no running instance

- **WHEN** no Hub process is running
- **THEN** `agentweave status` reports it as stopped without error

#### Scenario: Stop terminates a running instance cleanly

- **WHEN** a user runs `agentweave stop` while the Hub is running
- **THEN** the process is terminated and no run is left orphaned

#### Scenario: Reset recovers from a wedged state

- **WHEN** a user runs `agentweave reset` after confirming the destructive action
- **THEN** local Hub data is deleted and a subsequent bare invocation starts from a clean state

### Requirement: No CLI command manipulates collaboration state

The CLI SHALL provide no command that sends a message, creates or updates a task, asks or answers a
question, manages the agent roster, or manages scheduled jobs. Every such capability SHALL be
reachable only through the app UI (for the operator) or the agent capability plane (for an agent).

#### Scenario: Collaboration commands do not exist

- **WHEN** a user inspects the CLI's available commands
- **THEN** none of them sends a message, creates or updates a task, or manages agents or jobs
