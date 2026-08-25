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
