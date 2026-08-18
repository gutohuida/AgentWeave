## ADDED Requirements

### Requirement: The Hub runs natively on the host and owns agent execution

The Hub SHALL be installable and runnable as a host process with access to the operator's agent
CLI binaries, provider credentials, environment, and workspace. Containerized deployment SHALL
remain supported for coordination-only topologies but MUST NOT be the default for installations
that expect the Hub to launch agents.

When the Hub launches an agent it SHALL own the process lifecycle: spawn, output capture,
session identity, interruption, and exit status.

#### Scenario: A single command yields a running Hub that can launch agents

- **WHEN** an operator runs the documented start command on a machine with a supported agent CLI installed
- **THEN** the Hub starts, reports itself ready, and reports the agent CLI as launchable
- **AND** no separate watchdog, container runtime, or per-agent environment wiring is required

#### Scenario: Coordination-only deployment is explicit

- **WHEN** the Hub runs where it cannot reach a host agent CLI
- **THEN** it reports agents as not locally launchable with a stated reason
- **AND** it does not accept a trigger request that it cannot execute

### Requirement: Triggering an agent is direct and its outcome is observable

Triggering an agent SHALL execute it directly. The Hub MUST NOT represent a trigger as a message
to be discovered later by a polling process, and MUST NOT encode session directives as text inside
a message body.

A trigger request SHALL return a run identifier and a definite outcome: the run started, or it
failed with a stated reason. The Hub MUST NOT report a speculative or confidence-graded execution
status.

#### Scenario: A trigger starts a process and returns its identity

- **WHEN** a trigger request is accepted for a launchable agent
- **THEN** the Hub spawns the agent process before responding
- **AND** the response carries a run identifier usable to stream output and query status

#### Scenario: A failed launch is reported as a failure

- **WHEN** the agent binary is missing, unauthorized, or exits immediately on launch
- **THEN** the trigger fails with a stated reason
- **AND** no run is reported as started

#### Scenario: Session continuity is typed, not parsed from text

- **WHEN** a trigger requests resumption of a prior session
- **THEN** the session identifier travels as a typed field on the run record
- **AND** no session directive appears in any message body

#### Scenario: Polling is not the execution path

- **WHEN** any agent is triggered
- **THEN** execution does not depend on a periodic poll interval
- **AND** the observable delay between request and process start is not governed by a poller

### Requirement: Agent output streams live from the owned process

The Hub SHALL stream the output of agent processes it owns over its existing server-sent event
channel, as typed events describing run lifecycle and output.

#### Scenario: Output appears without a client poll

- **WHEN** an owned agent process writes output
- **THEN** connected clients receive it over the event stream
- **AND** clients do not poll a REST endpoint to discover it

#### Scenario: Run termination is reported

- **WHEN** an owned agent process exits, is interrupted, or fails
- **THEN** a terminal event carrying the outcome is emitted for that run

### Requirement: Manual connection ceremony is removed for Hub-managed agents

For agents the Hub manages, the operator SHALL NOT be required to copy a printed command, evaluate
shell exports, or supply a session identifier by hand. Provider environment resolution and session
continuity SHALL be handled by the Hub.

#### Scenario: An agent runs without shell preparation

- **WHEN** an operator triggers a configured agent from the Hub interface
- **THEN** the agent runs with correct provider environment and session continuity
- **AND** the operator performs no shell export, copy-paste, or session-identifier entry

### Requirement: Agents that write work in isolated checkouts

An agent that modifies files SHALL operate in a checkout isolated from every other agent's, sharing
the project's underlying version-control history. Two agents MUST NOT be able to write to the same
working copy of a file.

Where an agent's changes conflict with another's, the conflict SHALL be surfaced for resolution.
Changes MUST NOT be lost silently by one agent overwriting a file another agent had modified.

An agent that only reads MAY share the project's primary checkout.

#### Scenario: Concurrent writers cannot overwrite each other

- **WHEN** two agents in the same project modify the same file during overlapping turns
- **THEN** each writes only within its own checkout
- **AND** neither agent's changes are lost

#### Scenario: Divergent changes surface as a conflict

- **WHEN** two agents' changes to the same file are combined
- **THEN** the conflict is reported and available for resolution
- **AND** the interface identifies which agents diverged

#### Scenario: Isolation is prepared before the first turn

- **WHEN** an agent that writes is given work for the first time
- **THEN** its isolated checkout exists and is usable before the turn begins

#### Scenario: Isolation is released when an agent is removed

- **WHEN** an agent is removed from a project
- **THEN** its isolated checkout is released
- **AND** unmerged work is reported rather than discarded silently

### Requirement: Interrupted runs are reconciled and their entries returned

The Hub SHALL be able to determine, after restarting, whether a run recorded as active is still
executing. A run whose process is no longer present SHALL be recorded as interrupted.

Entries delivered to an interrupted run SHALL be returned to the agent's queue as undelivered, so
that no queued work is lost with the run that was carrying it.

When the Hub stops, it SHALL terminate the agent processes it started, leaving none running
unattended.

#### Scenario: A run that died is not reported as running

- **WHEN** the Hub restarts after an unexpected stop
- **THEN** any run whose process is absent is recorded as interrupted
- **AND** no run remains indefinitely in an active state

#### Scenario: Entries survive an interrupted run

- **WHEN** a run is interrupted after receiving its entries
- **THEN** those entries return to the queue as undelivered
- **AND** a following turn delivers them

#### Scenario: No agent process is orphaned

- **WHEN** the Hub stops
- **THEN** the agent processes it started are terminated

### Requirement: Turns are accounted in tokens, with currency reported as derived

Each turn SHALL record the token usage reported by its runner, and this SHALL be the primary unit of
accounting. Usage SHALL be aggregated per agent and per project.

Where a monetary figure is shown it SHALL be identified as an API-equivalent estimate and MUST NOT
be presented as the amount an operator has been charged. Where a runner reports remaining rate-limit
allowance, that allowance SHALL be shown in preference to a monetary figure.

A configurable token budget MAY be set per project. When it is exceeded, turns SHALL NOT start
autonomously, while operator-initiated turns remain available.

#### Scenario: Usage is recorded per turn and aggregated

- **WHEN** a turn completes
- **THEN** the token usage reported by its runner is recorded against that turn
- **AND** it is reflected in the totals for that agent and project

#### Scenario: Currency is never presented as an amount charged

- **WHEN** a monetary figure is displayed
- **THEN** it is identified as an API-equivalent estimate

#### Scenario: Subscription users see allowance rather than currency

- **WHEN** a runner reports remaining rate-limit allowance
- **THEN** that allowance is shown in place of a monetary figure

#### Scenario: An exhausted budget pauses autonomy but not the operator

- **WHEN** a project's token budget is exceeded
- **THEN** no turn starts autonomously
- **AND** the interface states that the budget is exhausted
- **AND** an operator-initiated turn still runs

#### Scenario: Missing usage data is reported, not invented

- **WHEN** a runner reports no usage for a turn
- **THEN** the turn shows usage as unavailable rather than as zero

### Requirement: The watchdog is limited to time-based duties

The watchdog SHALL NOT act as the transport for human- or Hub-initiated agent execution. It MAY
remain responsible for genuinely scheduled work.

#### Scenario: Scheduled jobs continue to fire

- **WHEN** a scheduled job reaches its due time
- **THEN** it executes through the Hub's direct execution path
- **AND** its outcome is observable in the same way as any other run

#### Scenario: Message scanning no longer triggers execution

- **WHEN** a message is created for an agent
- **THEN** no polling loop interprets that message as an instruction to spawn a process
