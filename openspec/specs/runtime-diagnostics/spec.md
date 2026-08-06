# runtime-diagnostics Specification

## Purpose
TBD - created by syncing change improve-runtime-diagnostics. Update Purpose after archive.
## Requirements
### Requirement: Runtime readiness checks
The system SHALL provide non-mutating readiness checks for the single native AgentWeave instance
without starting the Hub or making external model-provider API calls.

#### Scenario: Doctor reports instance readiness
- **WHEN** the user runs `agentweave doctor`
- **THEN** the system reports Python support, native Hub installation, runner CLIs on PATH, local port availability, SQLite database accessibility, and Hub-state file permissions

#### Scenario: Doctor runs before first launch
- **WHEN** the native Hub state directory does not exist
- **THEN** diagnostics inspect the nearest existing parent and do not create Hub state, a project, or a database

#### Scenario: Doctor does not expose secrets
- **WHEN** readiness checks inspect environment variables, transport configuration, runner commands, or proxy settings
- **THEN** the system reports variable names, paths, statuses, and hints without printing API key values, bearer tokens, or other secret values

---

### Requirement: Readiness check result model
The system SHALL represent each readiness check as a structured result with a stable check identifier, target, status, severity, user-facing message, and optional remediation hint.

#### Scenario: Check result includes actionable fields
- **WHEN** a readiness check detects a missing proxy API key
- **THEN** the result includes the check identifier, affected agent, status `fail`, severity `error`, the missing environment variable name, and a hint describing how to set it

#### Scenario: Check result can be rendered consistently
- **WHEN** the same readiness result is shown by `agentweave doctor` and `agentweave status`
- **THEN** the system uses the same status, severity, message, and hint semantics for that check

---

### Requirement: Proxy credential diagnostics
The Hub SHALL detect missing required proxy provider API key variables when agent configuration is
validated and before a proxy runner is spawned.

#### Scenario: Hub configuration reports missing proxy key
- **WHEN** a `claude_proxy` agent references a provider API key variable that is unavailable to the Hub process
- **THEN** the agent readiness response names the missing variable and explains how to provide it without exposing a secret value

#### Scenario: Hub trigger fails before spawn
- **WHEN** a run is requested for a proxy agent whose required provider API key variable is missing
- **THEN** the Hub refuses the run before spawn with an actionable typed conflict naming the missing variable

---

### Requirement: Watchdog launch preflight
The Hub SHALL run deterministic preflight checks before spawning an agent's run and SHALL refuse launches that are known to be impossible.

#### Scenario: Hub refuses proxy launch with missing key
- **WHEN** the Hub receives a trigger for a proxy agent whose required provider API key variable is missing
- **THEN** it does not spawn the process, returns a typed conflict response naming the missing variable, and records a structured diagnostic event

#### Scenario: Hub refuses launch with missing CLI
- **WHEN** the Hub receives a trigger for an agent whose runner CLI is not available in PATH
- **THEN** it does not spawn the process, returns a typed conflict response, and records a structured launch-skip diagnostic event

#### Scenario: A refused launch preserves state
- **WHEN** the Hub refuses a launch because a deterministic preflight check fails
- **THEN** the system preserves enough queued state for the user to retry after fixing the readiness issue

---

### Requirement: Structured diagnostic events
The system SHALL emit durable structured diagnostic events for runtime failures, degraded states, skipped execution, and unavailable dependencies.

#### Scenario: Non-fatal setup failure is logged
- **WHEN** a setup, synchronization, or registration step fails but the operation continues
- **THEN** the system emits a structured diagnostic event with the failing step, severity, message, and remediation hint when available

#### Scenario: Transport failure is classified
- **WHEN** an HTTP transport operation fails because the Hub is unreachable, authentication fails, a project is missing, a request times out, or the response is invalid
- **THEN** the system emits or returns a classified diagnostic rather than only a generic failure

#### Scenario: Agent process failure is summarized
- **WHEN** a launched agent subprocess exits with a non-zero status
- **THEN** the system records a structured diagnostic event containing agent name, runner type, exit code, duration when known, and a secret-safe summary of recent stderr

---

### Requirement: Hub trigger confidence reporting
The Hub SHALL distinguish queued agent work by execution confidence based on available agent and runner state.

#### Scenario: Trigger queued for manual agent
- **WHEN** the user triggers an agent whose runner is configured as manual
- **THEN** the response indicates that the message was queued for manual handling and does not imply automatic execution

---

### Requirement: Hub logs usability
The Hub Logs UI SHALL expose diagnostics in a way that reflects the current project rather than a fixed set of agents.

#### Scenario: Agent filter includes actual agents
- **WHEN** the Hub Logs view is opened
- **THEN** the agent filter includes agents from configured session data, self-registered agents, or returned log entries, including custom agents and proxy agents

#### Scenario: Diagnostic category filters exist
- **WHEN** diagnostic events exist in the log stream
- **THEN** the user can filter or search common categories such as runner, proxy credentials, setup, jobs, and agent stderr

#### Scenario: Log detail remains secret-safe
- **WHEN** a log entry contains diagnostic data derived from env vars, transport config, or runner commands
- **THEN** the UI does not display secret values

---

### Requirement: Job failure diagnostics
The system SHALL make scheduled and manually fired job failures durable and visible.

#### Scenario: Job run failure records summary
- **WHEN** a job run fails to start, fails to trigger an agent, or raises an internal scheduler error
- **THEN** the system records the run as failed with a secret-safe error summary and emits a structured diagnostic event

#### Scenario: Job UI can distinguish failed from idle
- **WHEN** a job has a recent failed run
- **THEN** the Hub job view exposes that failed state separately from jobs that are merely disabled, pending, or idle

---

### Requirement: Agent readiness summary
The Hub SHALL summarize readiness so users can see whether configured agents are immediately usable.

#### Scenario: Hub exposes agent readiness
- **WHEN** the operator inspects configured agents
- **THEN** the Hub exposes a compact readiness summary for each agent covering runner type, CLI availability, required environment variables, context status, and overall readiness

#### Scenario: Hub records degraded readiness
- **WHEN** one or more readiness checks warn or fail
- **THEN** the Hub records structured diagnostic events and exposes remediation hints to the operator

---

### Requirement: Collaboration readiness is checkable before it is needed

The Hub SHALL be able to report, for a project's agents, whether agent-to-agent collaboration will
actually work — not merely whether the runner CLI is installed and authorized.

The report SHALL cover whether the tool surface will be invocable by that agent's provider, and
whether the address supplied to runs is the address the Hub is serving on. Each unmet condition
SHALL name what is wrong in terms an operator can act on.

This check MUST NOT require starting an agent run.

#### Scenario: An agent that cannot use its tools is reported

- **WHEN** collaboration readiness is reported for an agent whose provider would refuse its tool calls
- **THEN** the agent is reported as not collaboration-ready
- **AND** the reason names the refusal

#### Scenario: A mismatched callback address is reported

- **WHEN** the address the Hub would supply to runs is not the address it is serving on
- **THEN** collaboration readiness reports the mismatch
- **AND** names both addresses

#### Scenario: Readiness does not spawn agents

- **WHEN** collaboration readiness is reported
- **THEN** no agent run is started
