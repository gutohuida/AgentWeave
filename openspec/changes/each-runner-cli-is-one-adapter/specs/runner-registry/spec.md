## ADDED Requirements

### Requirement: Each supported runner CLI is served by exactly one runner adapter

The Hub SHALL decide everything that differs between runner CLIs through one adapter per supported CLI, and the set of supported CLIs SHALL be the set of adapters, equal to the CLIs a runner record may name, the CLIs the database accepts, and the providers the model catalog declares.

The things that differ between runner CLIs are:
- how a turn is launched and over which transport, how its output becomes events, and how its usage and
  context window are read;
- how the Hub's tool server is injected into it, and how the rendered context reaches it;
- how a permission posture is expressed to it, and which tool calls of it write files;
- whether its binary is present and authorised, and whether a triggered run can collaborate;
- its one-shot invocation for workers and titles;
- which catalog provider it renders.

Code outside the adapters SHALL NOT branch on a runner CLI's name. A runner CLI with no adapter SHALL NOT be accepted
for a runner record. A runner string with no adapter that arrives from a legacy configuration SHALL be reported
unlaunchable, or launched by no one. It SHALL never be spawned through another CLI's adapter.

Adding a supported CLI is adding one adapter and registering it, together with the catalog provider and the
database's accepted set. These four agree or the Hub's own tests fail.

Moving existing runners onto adapters SHALL NOT change any of the following for a run on those runners:
- the command line it is launched with;
- the events recorded from its output;
- its permission posture;
- its launchability or collaboration verdict;
- anything an API returns about it.

#### Scenario: The supported set is the adapter set

- **WHEN** the Hub starts
- **THEN** the CLIs that have an adapter, the CLIs a runner may name, the CLIs the database accepts, and the model
  catalog's providers are the same set
- **AND** today that set is `claude` and `codex`

#### Scenario: A runner CLI with no adapter is refused

- **WHEN** an operator attempts to create a runner naming a CLI that has no adapter
- **THEN** the Hub rejects the request

#### Scenario: A legacy runner string is not spawned through another adapter

- **WHEN** an agent's configuration names a runner string that has no adapter
- **THEN** its launchability is decided without any adapter
- **AND** no run of it is started through another CLI's adapter

#### Scenario: Moving a runner onto its adapter changes nothing it does

- **WHEN** a Claude or Codex run is started after the move, with the same configuration, flags, posture and prompt as before it
- **THEN** its command line is byte-identical to the one built before the move
- **AND** the events recorded from the same output are identical

#### Scenario: A transport sentinel is stripped whichever runner carries it

- **WHEN** any runner's flags contain a transport sentinel that any adapter declares
- **THEN** the command the Hub builds for that runner does not contain the sentinel
