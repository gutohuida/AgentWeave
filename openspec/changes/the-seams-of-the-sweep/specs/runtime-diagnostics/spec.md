## ADDED Requirements

### Requirement: The documented command form is the one that works

Where the command-line help documents an option before the subcommand, that form SHALL take effect.
An option that is accepted and silently ignored SHALL NOT exist: either it works, or it is refused
with a statement of the form that does work.

Measured 2026-08-25 against a Hub confirmed live: the documented form reported the Hub **stopped**
while the undocumented form reported it running. Neither errored, so the operator had no signal that
the flag went nowhere — they were simply told the service was down while it was serving requests.

#### Scenario: The option is given before the subcommand
- **WHEN** the operator supplies the port option in the position the help documents
- **THEN** it SHALL take effect

#### Scenario: The option is given in both positions
- **WHEN** the operator supplies the option both before and after the subcommand
- **THEN** the value nearer the subcommand SHALL win

#### Scenario: The reported state matches reality
- **WHEN** a Hub is serving requests on the named port
- **THEN** it SHALL be reported running

### Requirement: A running instance is described as what it actually is

Diagnostics SHALL describe a running instance by how it is actually running, and SHALL examine the
instance the project is bound to rather than a default.

Today a native process is reported as Docker, and `doctor`, run from inside a project bound to a
non-default port, checks the default port and a database nobody serves — then returns all checks
passing without having examined the running instance at all. A clean bill of health that inspected
the wrong thing is worse than no report.

#### Scenario: A natively started instance
- **WHEN** an instance was started as a local process rather than in a container
- **THEN** it SHALL be reported as native

#### Scenario: Diagnostics inside a bound project
- **WHEN** diagnostics run inside a project bound to a particular instance
- **THEN** they SHALL examine that instance's port and database

#### Scenario: Diagnostics cannot reach the bound instance
- **WHEN** the bound instance cannot be reached
- **THEN** that SHALL be reported as a failure rather than omitted from the summary

### Requirement: A silently degraded environment SHALL be reported once, where it can be acted on

Where the Hub deliberately degrades rather than failing, `doctor` SHALL report the degraded
condition, name its consequence in terms the operator will meet it in, and name the remedy.

Degrading is often correct — failing a whole turn because a shared dependency directory could not be
linked into an agent's worktree would be worse than provisioning without it. What is not correct is
that nobody is told. Measured on this machine: directory symlinks cannot be created without an extra
privilege, so **every** agent worktree is provisioned without the project's installed dependencies,
and no surface says so. The agent discovers it by running the suite and failing. The operator sees a
checkout that looks complete. The diagnostic did not look.

It stayed invisible while the fixtures were projects whose tooling was already on the path, and
stops being invisible the moment a reviewer is handed a checkout *because it can run the tests* —
that reviewer then reports that it could not run the suite, and is telling the truth about an
environment nobody told it about.

#### Scenario: The environment cannot support a facility the Hub relies on
- **WHEN** diagnostics run on a machine where that facility is unavailable
- **THEN** the report SHALL include a warning naming the facility and what will be missing without it
- **AND** SHALL name the remedy

#### Scenario: The facility is available
- **WHEN** diagnostics run on a machine where it works
- **THEN** the report SHALL say so and SHALL NOT warn

#### Scenario: Degraded is not failed
- **WHEN** the facility is unavailable but the Hub is otherwise ready
- **THEN** the condition SHALL be reported as a warning and SHALL NOT be reported as a failure

#### Scenario: The probe leaves no trace
- **WHEN** the diagnostic tests the facility
- **THEN** it SHALL not leave anything behind in the location it probed
