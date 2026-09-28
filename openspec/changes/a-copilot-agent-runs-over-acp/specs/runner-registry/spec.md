## MODIFIED Requirements

### Requirement: Runners are project-scoped Hub records

The Hub SHALL persist runner definitions as project-scoped database rows, each identifying a
supported CLI (`claude`, `codex` or `copilot`), optional launch flags, and an optional default model.
A runner SHALL NOT be represented only as an in-memory or hardcoded mapping.

The set of supported CLIs SHALL be enforced identically by the request validator and by the
database, so a CLI the validator accepts is never refused by a database constraint.

#### Scenario: Runner is created

- **WHEN** an operator creates a runner naming a supported CLI
- **THEN** the Hub persists it as a project-scoped record with a stable identifier

#### Scenario: A Copilot runner is created

- **WHEN** an operator creates a runner naming `copilot`
- **THEN** the Hub persists it as a project-scoped record with a stable identifier
- **AND** the database accepts the row

#### Scenario: Only supported CLIs are accepted

- **WHEN** an operator attempts to create a runner naming a CLI other than `claude`, `codex` or `copilot`
- **THEN** the Hub rejects the request

### Requirement: Built-in runners are seeded on first use

A project with zero runner records SHALL be seeded with one default runner per supported CLI before
any agent can be bound to a runner.

#### Scenario: First boot seeds default runners

- **WHEN** a project has no runner records and the Hub starts
- **THEN** the Hub creates a default `claude` runner, a default `codex` runner and a default `copilot` runner for that project

#### Scenario: A project that already has runners is not re-seeded

- **WHEN** a project already has at least one runner record and the Hub starts
- **THEN** the Hub creates no runner for it, including no `copilot` runner

## ADDED Requirements

### Requirement: A Copilot runner is spawned as its own executable

The Hub SHALL spawn a Copilot run by the Copilot CLI's native executable, never through an npm or script shim, and SHALL say which path it looked for when it cannot find one.

A shim runs a second process in front of the CLI. Stopping the shim can leave the CLI running. The
Hub SHALL resolve, in order:

1. a runner's pinned executable;
2. a `copilot` on `PATH` that is itself a native executable;
3. the platform binary inside the npm package that a `copilot` shim on `PATH` belongs to.

#### Scenario: An npm-installed Copilot on Windows

- **WHEN** `copilot` on `PATH` is the npm `copilot.cmd` shim
- **THEN** the Hub spawns `node_modules\@github\copilot\node_modules\@github\copilot-win32-x64\copilot.exe` beside it
- **AND** the spawned command's first argument is that executable, not the shim

#### Scenario: A Copilot agent is triggered

- **WHEN** an operator triggers an agent bound to a `copilot` runner on a machine where the Copilot CLI is installed and signed in
- **THEN** the Hub does not refuse the turn as an unsupported runner
- **AND** the spawned Copilot process is configured with the Hub's `agentweave` MCP server

#### Scenario: A shim whose platform binary is missing

- **WHEN** a `copilot` shim is on `PATH` and its package holds no binary for this platform
- **THEN** launchability reports the runner not present
- **AND** the reason names the path the Hub looked for

### Requirement: A Copilot runner below the supported version is refused

The Hub SHALL refuse to run a turn on a Copilot CLI older than its supported minimum version, 1.0.81, reading the version the CLI reports in its protocol handshake, and SHALL fail that turn before any session is created.

The version the Hub reads SHALL be the version that runs. The Hub SHALL spawn the CLI with automatic
updates disabled, so a cached newer package cannot run in place of the version it checked.

#### Scenario: An old CLI is refused

- **WHEN** a Copilot turn starts and the CLI reports version 1.0.75
- **THEN** the run fails with a reason naming 1.0.75, the supported minimum and how to update
- **AND** no Copilot session was created for the conversation

#### Scenario: A supported CLI proceeds

- **WHEN** a Copilot turn starts and the CLI reports version 1.0.88
- **THEN** the turn proceeds to create or load its session

#### Scenario: A missing version is treated as too old

- **WHEN** the CLI's handshake reports no version
- **THEN** the run fails as for a version below the minimum

### Requirement: A Copilot turn that fails after its prompt ends as a failed turn, not a failed start

Once a Copilot turn's prompt has been sent, the Hub SHALL record any failure of that turn as the run's failed outcome, keeping what the turn wrote, and SHALL NOT treat it as a turn that never started.

A failure after the prompt includes an error answer to the prompt, the Copilot process ending, the
turn timing out, and an error Copilot reports for the session's own agent during the turn. Copilot
can report such an error and still say the turn ended normally. The Hub SHALL then record the turn
as failed with Copilot's message, unless the turn was stopped. An error Copilot reports for a
subagent the turn started SHALL be recorded in the run's timeline and SHALL NOT by itself fail the
turn. A failure before the prompt SHALL still be
recorded as a failure to start. When that failure is Copilot reporting that it is not signed in
or is too old, the Hub SHALL record that verdict for the runner before the input is retried. The
retry is then held instead of failing the same way again.

#### Scenario: The prompt is answered with an error after the agent worked

- **WHEN** a Copilot turn has written a file in its worktree and its prompt is then answered with an error
- **THEN** the run ends failed with that error
- **AND** the worktree is snapshotted as for any finished turn

#### Scenario: A session error with a normal ending

- **WHEN** Copilot reports a session error during a turn and then ends the turn normally
- **THEN** the run ends failed with the session error's message

#### Scenario: A subagent's error with a normal ending

- **WHEN** Copilot reports an error for a subagent the turn started, and then ends the turn normally with no error for the session's own agent
- **THEN** the run does not end failed on that account
- **AND** the subagent's error appears in the run's timeline

#### Scenario: A sign-in failure holds the input

- **WHEN** a Copilot turn fails because Copilot is not signed in
- **THEN** the runner is reported not authorized with the `copilot login` sentence
- **AND** the operator's input stays queued without a delivery attempt being counted against it

### Requirement: Copilot launchability is read from Copilot itself

The Hub SHALL decide whether a Copilot runner is authorized by asking the Copilot CLI, and SHALL NOT decide it from GitHub token variables in the Hub's own environment.

The Copilot CLI keeps its sign-in in the operating system's credential store. A token variable in the
environment overrides that sign-in instead of proving it exists. The Hub SHALL reach its verdict
without a model call. It SHALL report a CLI that is not signed in, and a CLI below the supported
version, as not authorized, each with a reason that says what to do. A verdict the Hub has not yet
computed SHALL NOT make a Copilot agent uncreatable. In that case the run's own handshake is the
binding check. A verdict that the CLI is not signed in or is too old SHALL be checked again on the
next read of it, so that signing in or updating is seen without waiting for the verdict to age.

#### Scenario: A signed-in Copilot with no token variables

- **WHEN** the Hub's environment has no `GH_TOKEN`, `GITHUB_TOKEN` or `COPILOT_GITHUB_TOKEN` and the Copilot CLI is signed in
- **THEN** a Copilot runner is reported launchable

#### Scenario: A Copilot CLI that is not signed in

- **WHEN** the Copilot CLI refuses to create a session because no sign-in exists
- **THEN** a Copilot runner is reported not authorized
- **AND** the reason says to run `copilot login`

#### Scenario: Signing in is seen at once

- **WHEN** the Hub holds a verdict that the Copilot CLI is not signed in, and the operator then runs `copilot login`
- **THEN** the next read of the verdict starts a new check
- **AND** a read after that check completes reports the runner launchable

#### Scenario: The verdict is still being computed

- **WHEN** an operator creates a Copilot agent before the Hub has finished its first Copilot probe
- **THEN** creation is not refused on that account
