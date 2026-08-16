# app-lifecycle

## MODIFIED Requirements

### Requirement: Bare invocation is the only entry point

Running `agentweave` with no subcommand SHALL launch or reuse the one local AgentWeave runtime,
open or register the invocation directory as a project through that runtime, and open the app at
that project's overview. This SHALL be the only supported way to begin using AgentWeave.

The one local AgentWeave runtime SHALL resolve to the same database and instance state regardless
of which directory it was launched from, whether started through `agentweave hub-start`, a direct
`uvicorn hub.main:app` invocation, or `docker compose up` against the Hub's compose file. Only the
directory-scoped *project* registered against that runtime SHALL vary by launch directory.

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

#### Scenario: The Hub's own database is launch-directory-independent

- **WHEN** the Hub is started via a direct `uvicorn hub.main:app` invocation with no
  `DATABASE_URL` set, from two different working directories, on two separate occasions
- **THEN** both invocations resolve to the same absolute database path under the user's home
  directory, not a path relative to the working directory either was launched from

#### Scenario: Docker Compose produces the same instance regardless of launch directory

- **WHEN** `docker compose up` is run against the Hub's compose file from two different host
  directories
- **THEN** both invocations resolve to the same named Compose project and the same `hub-data`
  volume, not a volume prefixed by whichever directory's name happened to be current

## ADDED Requirements

### Requirement: The app flag opens a dedicated desktop window when a native webview is available

The system SHALL open `--app` in a dedicated window with no browser chrome (no address bar, no
tabs) and its own OS taskbar/dock presence, rather than a browser tab or window, when a native
webview backend (`pywebview`, an optional extra) is installed and can create a window.

When no native webview backend is installed, or window creation fails for any reason (missing
platform runtime, no display), the system SHALL fall back to the existing chromeless-browser-or-
default-browser-tab behavior without error, and SHALL NOT crash the invoking `hub-start` command.

The invoking process SHALL remain running for as long as the native desktop window is open, and
SHALL exit once the operator closes it. The detached Hub backend process itself SHALL be
unaffected by the window closing — closing the window MUST NOT stop the Hub.

#### Scenario: A native window opens when the backend is available

- **WHEN** `agentweave hub-start --app` is run with a working native webview backend installed
- **THEN** a single window opens with no browser chrome, titled for the app
- **AND** the invoking command does not return until that window is closed

#### Scenario: Falls back to a browser window when the backend is absent

- **WHEN** `agentweave hub-start --app` is run with no native webview backend installed
- **THEN** the system opens the Hub in a chromeless app-mode browser window or the default browser,
  exactly as it did before the native backend existed
- **AND** the invoking command returns without waiting for that window to close

#### Scenario: Falls back when the backend is installed but cannot create a window

- **WHEN** a native webview backend is installed but raises an error while creating or starting the
  window (for example, no compatible platform runtime is present)
- **THEN** the system reports what could not be created
- **AND** falls back to the browser-window behavior instead of exiting with an unhandled error

#### Scenario: Closing the window does not stop the Hub

- **WHEN** the operator closes a native app window opened by `--app`
- **THEN** the detached Hub backend process remains running and reachable
