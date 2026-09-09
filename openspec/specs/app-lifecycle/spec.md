# app-lifecycle Specification

## Purpose

Defines the single supported way to begin and manage a local AgentWeave instance: bare `agentweave`
invocation as the only entry point, plus `doctor`/`status`/`stop`/`reset` for diagnosing and managing
that instance. Originated by `openspec/changes/single-runtime`, which also removed every CLI command
that manipulated collaboration state directly.
## Requirements
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

### Requirement: No CLI command manipulates collaboration state

The CLI SHALL provide no command that sends a message, creates or updates a task, asks or answers a
question, manages the agent roster, or manages scheduled jobs. Every such capability SHALL be
reachable only through the app UI (for the operator) or the agent capability plane (for an agent).

#### Scenario: Collaboration commands do not exist

- **WHEN** a user inspects the CLI's available commands
- **THEN** none of them sends a message, creates or updates a task, or manages agents or jobs

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

### Requirement: A shutting-down instance SHALL release its database connections before its event loop closes
A local AgentWeave instance SHALL, while its event loop is still running, settle the background run tasks it started and then release every database connection it holds, so that no connection outlives the loop that last queued work on it.

Order is part of the requirement, not an implementation choice. Releasing the connections while a
background run is still writing takes away the connection that run needs to finish, so it never
finishes; settling the runs after the connections are gone is the same mistake in the other
direction. Terminating the run *processes*, which shutdown already does first, does not settle the
in-process tasks that were driving them.

The instance SHALL also stop admitting new scheduled work before it settles, so that the settle is
not racing a scheduler that can still start a run. Stopping the scheduler does not wait for a job
already in flight, and such a job can start a run of its own, so a settle performed first is
settling a set that can be refilled behind it.

Settling SHALL tolerate a run that schedules a successor while it is being settled — releasing a
run's input can legitimately schedule the same agent again — and SHALL be bounded, so that a
repeatedly rescheduling agent cannot hold the instance open. Reaching that bound is a reportable
condition, not a fatal one: an instance that has been asked to stop SHALL stop.

Releasing the connections SHALL itself be incapable of blocking indefinitely. This is not a
restatement of the bound above: the release is what closes each connection, and closing a
connection whose driver worker has ended is unbounded work on a thread that is gone. An instance
that has been asked to stop SHALL stop applies to this step as much as to the settle, and it is the
next requirement that makes it true.

This requirement governs a shutdown that runs at all. A forced termination of the instance's
process — one that delivers no signal the process can act on — runs no shutdown sequence, and this
requirement makes no claim about it.

#### Scenario: A run still writing when the instance is asked to stop

- **WHEN** the instance is shut down while a background run task is in flight
- **THEN** the run task is settled and every database connection is released before the event loop
  closes
- **AND** the shutdown produces no uncaught error from a database driver's worker thread

#### Scenario: A scheduled job fires as the instance is stopping

- **WHEN** the instance is shut down while a scheduled job is in flight
- **THEN** the scheduler stops admitting work before the background run tasks are settled
- **AND** any run that job started is settled with the rest

#### Scenario: A run reschedules while shutdown is settling it

- **WHEN** settling a background run task releases its input and that release schedules another run
- **THEN** shutdown settles the successor as well, up to a bounded number of passes

#### Scenario: Settling does not complete within the bound

- **WHEN** background run tasks are still being registered after the bounded number of passes
- **THEN** the instance records how many remain and completes its shutdown anyway

#### Scenario: A connection whose driver worker is already gone is held at shutdown

- **WHEN** the instance releases its database connections and one of them can no longer complete
  work
- **THEN** the release does not wait on it
- **AND** the shutdown completes

### Requirement: A database connection whose driver worker is gone SHALL be replaced, never reused
The instance SHALL NOT hand out a pooled database connection that can no longer complete work, SHALL replace it with a new connection instead, and SHALL NOT wait on such a connection when disposing of it.

An asynchronous SQLite connection carries out every statement on one dedicated worker thread. If
that thread has ended, the connection is not slow and is not merely in an error state: it accepts
work, never answers, and cannot be closed, because closing is itself work for the thread that ended.
Anything that waits on it waits without bound, and cancelling the wait does not return either,
because unwinding the connection needs the same thread.

Detection therefore SHALL happen before the connection is handed out rather than after a statement
has already been issued on it, and discarding such a connection SHALL NOT require the connection to
answer — it is put beyond use first, then discarded, so that the instance's own cleanup cannot block
on it.

Putting it beyond use SHALL cover every path that closes such a connection, not only the one that
detected it. Handing out is one of several things an instance does with a pooled connection:
it also releases the whole pool at shutdown, and it disposes of a connection it has given up on
after replacement was attempted and did not succeed. Each of those closes the connection, and each
therefore has the same unbounded wait available to it. A detection sited only where connections are
handed out leaves the release path unprotected, which is the path the previous requirement depends
on.

Replacement SHALL be transparent to the caller: work issued after a dead connection is discarded
completes against a fresh connection rather than failing.

This requirement holds wherever the condition arises. It is not conditional on the instance having
been shut down, and it applies to a connection whose worker was lost for any reason.

#### Scenario: A pooled connection whose worker thread has ended

- **WHEN** a database connection whose driver worker thread has ended is next taken from the pool
- **THEN** it is discarded without any statement being issued on it
- **AND** the request is served by a newly opened connection
- **AND** the statement completes

#### Scenario: Discarding does not wait on the dead connection

- **WHEN** such a connection is discarded
- **THEN** neither the discard nor any cleanup it triggers waits on the ended worker thread

#### Scenario: Releasing the pool does not wait on the dead connection

- **WHEN** the instance releases every connection it holds and one of them has an ended worker
  thread
- **THEN** the release completes without waiting on that thread
- **AND** it is not necessary for that connection to have been handed out first for this to hold

#### Scenario: A connection given up on after replacement is not waited on either

- **WHEN** replacement is attempted the bounded number of times and the checkout is abandoned
- **THEN** disposing of the connection it was abandoned on does not wait on an ended worker thread
- **AND** the caller receives an error rather than an unbounded wait

#### Scenario: A healthy connection is unaffected

- **WHEN** a database connection whose driver worker thread is running is taken from the pool
- **THEN** it is used as-is and no reconnection occurs

#### Scenario: A driver that does not present a worker thread

- **WHEN** the instance is configured against a database driver that has no per-connection worker
  thread
- **THEN** connections are taken from the pool unchanged and the check does not fail the checkout
