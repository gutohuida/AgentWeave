## MODIFIED Requirements

### Requirement: Bare invocation is the only entry point

Running `agentweave` with no subcommand SHALL launch or reuse the one local AgentWeave runtime,
open or register the invocation directory as a project through that runtime, and open the app at
that project's overview. This SHALL be the only supported way to begin using AgentWeave.

The one local AgentWeave runtime SHALL resolve to the same database and instance state regardless
of which directory it was launched from, whether started through bare `agentweave` (with or without
`--docker`/`--local`), a direct `uvicorn hub.main:app` invocation, or `docker compose up` against the
Hub's compose file. Only the directory-scoped *project* registered against that runtime SHALL vary by
launch directory.

That guarantee SHALL hold for every launch path that says which database it wants, and SHALL NOT be
discharged by guessing on behalf of one that does not. **A runtime that was not told which database
to open SHALL refuse to open one**, rather than falling back to the path bare `agentweave` would have
used. A missing instruction and a deliberate choice of the default path are different states and MUST
NOT produce the same outcome, because the default path is where an operator's real work lives and a
process that reaches it by accident migrates and writes to it exactly as one that reached it on
purpose.

The refusal SHALL name the path it declined to open and SHALL name both supported ways to say what to
open. It SHALL occur before the runtime opens, creates, or migrates any database file.

A runtime that *was* told which database to open SHALL state the absolute path it resolved and
whether that file already existed. When the runtime's server process is itself the first thing to
touch that database, it SHALL state this **before** opening it. That statement SHALL be emitted at a
level the runtime's default logging configuration actually shows, and SHALL be intelligible on its
own, so that an unintended attachment is readable at the moment it happens rather than inferred
afterwards from output that is missing.

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

#### Scenario: A runtime that was not told which database to open refuses to open one

- **WHEN** the Hub is started via a direct `uvicorn hub.main:app` invocation, from any working
  directory, with no `DATABASE_URL` in the environment and none supplied by an environment file
- **THEN** the runtime fails to start, without opening, creating or migrating any database file
- **AND** the failure names the absolute path it declined to open, names `DATABASE_URL` as the way to
  say which database to open, and names bare `agentweave` as the way to get that default deliberately

#### Scenario: A told database is named before it is opened

- **WHEN** the Hub is started by a direct `uvicorn hub.main:app` invocation with a database it was
  told to open, by environment variable or by an environment file
- **THEN** it states the resolved absolute path and whether that file already existed, before it
  creates a directory, creates a file, or applies a migration to it
- **AND** that statement appears in the runtime's output under its own default logging configuration,
  with no additional flag or configuration required, and names what it is without depending on a
  logger-name or level prefix being present

#### Scenario: A told database is named on every other launch path too

- **WHEN** the Hub is started through bare `agentweave` or `docker compose up`, both of which apply
  migrations in a separate step before the server process starts
- **THEN** the server process still states the resolved absolute path and whether that file already
  existed
- **AND** it is not required to do so before that separate migration step, which has already run

#### Scenario: An explicitly named database is opened whatever path it names

- **WHEN** the Hub is started with `DATABASE_URL` naming the same path bare `agentweave` would have
  resolved to
- **THEN** it opens that database and does not refuse, because the instruction was given rather than
  guessed

#### Scenario: The database a launch path names does not depend on its working directory

- **WHEN** a launch path supplies a database path of its own that is resolved on the host — bare
  `agentweave`, or `agentweave --profile <name>`
- **THEN** that path is absolute, and two invocations from two different working directories resolve
  to the same file

#### Scenario: A container's own relative database path is not a host path

- **WHEN** the Hub ships an environment file or compose file whose `DATABASE_URL` is relative, for
  resolution against a fixed working directory inside a container image
- **THEN** that value is left relative, because it names a mount point rather than a host location
- **AND** the file states that it is a container path, so that copying it into a source checkout is
  recognisably a change that must supply an absolute path instead

#### Scenario: Docker Compose produces the same instance regardless of launch directory

- **WHEN** `docker compose up` is run against the Hub's compose file from two different host
  directories
- **THEN** both invocations resolve to the same named Compose project and the same `hub-data`
  volume, not a volume prefixed by whichever directory's name happened to be current
