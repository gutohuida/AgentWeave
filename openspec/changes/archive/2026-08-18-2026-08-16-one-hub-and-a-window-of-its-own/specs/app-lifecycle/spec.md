# app-lifecycle

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

### Requirement: App mode opens a dedicated desktop window when a native webview is available

The system SHALL open app mode in a dedicated window with no browser chrome (no address bar, no
tabs) and its own OS taskbar/dock presence, rather than a browser tab or window, when a native
webview backend (`pywebview`, an optional extra) is installed and can create a window.

App mode is not an opt-in flag — it is forced on for bare `agentweave` invocation, the CLI's only
entry point, and for its `--docker`/`--local` branch equally. This requirement therefore governs the
**default** behavior of every normal launch, not a feature an operator must ask for.

This applies
uniformly to every launch path that reaches app mode — native (`agentweave`) and Docker
(`agentweave --docker`, `agentweave --local`) alike; neither is exempt. This uniformity is about the
native-vs-Docker launch path specifically, not about detached vs. foreground process mode: the
foreground (`--no-detach`) start path is a separate, narrower exception, stated below, because a
native webview's event loop must run on the process's main thread, and `--no-detach` already commits
that thread to blocking in the backend server until the operator interrupts it.

When no native webview backend is installed, or window creation fails for any reason (missing
platform runtime, no display), the system SHALL fall back to the existing chromeless-browser-or-
default-browser-tab behavior without error, and SHALL NOT crash the invoking command.

The invoking process SHALL remain running for as long as the native desktop window is open, and
SHALL exit once the operator closes it. The detached Hub backend process itself SHALL be
unaffected by the window closing — closing the window MUST NOT stop the Hub.

A foreground (`--no-detach`) start SHALL be exempt from opening a native desktop window, regardless
of whether a native webview backend is installed — it SHALL continue to use the existing
chromeless-browser-or-default-browser-tab behavior for app mode, unchanged by this requirement. This
exemption exists because `--no-detach` keeps the backend server itself in the foreground, occupying
the one thread a native webview's event loop would need; Ctrl+C on that foreground server remains the
only stop mechanism for a `--no-detach` start, exactly as before this change.

#### Scenario: A native window opens when the backend is available

- **WHEN** bare `agentweave` is run with a working native webview backend installed
- **THEN** a single window opens with no browser chrome, titled for the app
- **AND** the invoking command does not return until that window is closed

#### Scenario: A native window opens for a Docker-launched instance too

- **WHEN** `agentweave --docker` (or `agentweave --local`) is run with a working native webview
  backend installed
- **THEN** a single window opens with no browser chrome, exactly as it does for a native launch —
  the Docker branch is not exempt from app mode

#### Scenario: Falls back to a browser window when the backend is absent

- **WHEN** bare `agentweave` is run with no native webview backend installed
- **THEN** the system opens the Hub in a chromeless app-mode browser window or the default browser,
  exactly as it did before the native backend existed
- **AND** the invoking command returns without waiting for that window to close

#### Scenario: Falls back when the backend is installed but cannot create a window

- **WHEN** a native webview backend is installed but raises an error while creating or starting the
  window (for example, no compatible platform runtime is present)
- **THEN** the system reports what could not be created
- **AND** falls back to the browser-window behavior instead of exiting with an unhandled error

#### Scenario: Closing the window does not stop the Hub

- **WHEN** the operator closes a native app window opened in app mode
- **THEN** the detached Hub backend process remains running and reachable

#### Scenario: A foreground (`--no-detach`) start keeps the browser fallback

- **WHEN** `agentweave --no-detach` is run with a working native webview backend installed
- **THEN** the system still opens the existing chromeless-browser-or-default-browser-tab behavior for
  app mode, not a native window
- **AND** the foreground `uvicorn` server keeps running attached to the invoking terminal, stopped
  only by Ctrl+C, exactly as it did before this change

### Requirement: A named profile selects a separate, deliberate instance

The system SHALL accept a `--profile <name>` argument on `agentweave`, `agentweave status`, and
`agentweave stop`, defaulting to `"default"` when omitted. A profile SHALL resolve to its own
database path and its own PID file, independent of every other profile's.

The default profile SHALL resolve to the same database path this capability already specifies
(unaffected by this requirement — no existing install migrates). A named profile other than
`"default"` SHALL resolve to a database path beneath `~/.agentweave/hub/profiles/<name>/`, distinct
from the default profile's path and from every other named profile's.

An explicit `DATABASE_URL` environment variable SHALL continue to override whatever path profile
resolution would otherwise compute, exactly as it does today without `--profile`.

A `--profile <name>` value other than `"default"` SHALL require an explicit `--port` argument. If
`--port` was not explicitly given, the system SHALL exit with an error naming both flags rather than
silently resolving to the default port, because that default port is the same one the default
profile normally runs on.

`agentweave reset` SHALL target only the default profile's data unless invoked with
`--profile <name>`, in which case it SHALL target only that named profile's data. `agentweave reset`
SHALL NOT delete more than one profile's data in a single invocation.

#### Scenario: Two profiles do not collide

- **WHEN** `agentweave --profile a --port 8010` and `agentweave --profile b --port 8011` are both
  running at once
- **THEN** each resolves to its own database file and its own PID file
- **AND** `agentweave stop --profile a` stops only the `a` profile's instance, leaving `b` running

#### Scenario: The default profile is unaffected by profile support existing

- **WHEN** `agentweave` is run with no `--profile` argument
- **THEN** it resolves to exactly the database path this capability already specifies for bare
  invocation, unchanged by the existence of named profiles

#### Scenario: An explicit DATABASE_URL still wins over profile resolution

- **WHEN** `agentweave --profile a` is run with `DATABASE_URL` set in the environment
- **THEN** the system uses the `DATABASE_URL` value, not the path profile `a` would otherwise resolve
  to
- **AND** the system states which one took effect

#### Scenario: Reset targets exactly one profile

- **WHEN** `agentweave reset --profile a` is run while profiles `a` and `b` both have data
- **THEN** only profile `a`'s data is deleted
- **AND** profile `b`'s data is untouched

#### Scenario: A named profile without an explicit port is rejected

- **WHEN** `agentweave --profile dev` is run with no `--port` argument
- **THEN** the system exits with an error naming both `--profile` and `--port`
- **AND** it does not start a Hub instance on the default port
