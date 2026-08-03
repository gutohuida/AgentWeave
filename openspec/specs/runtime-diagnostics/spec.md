# runtime-diagnostics Specification

## Purpose
TBD - created by syncing change improve-runtime-diagnostics. Update Purpose after archive.
## Requirements
### Requirement: Runtime readiness checks
The system SHALL provide runtime readiness checks for the current AgentWeave project without requiring Hub mode or external model-provider API calls.

#### Scenario: Doctor reports project readiness
- **WHEN** the user runs `agentweave doctor`
- **THEN** the system reports readiness checks for session state, project config, Hub connectivity, configured agents, runner CLIs, proxy API key variables, context files, MCP setup indicators, and configured jobs

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
The system SHALL detect missing required proxy provider API key variables before a proxy runner is used.

#### Scenario: Configure warns about missing proxy key
- **WHEN** the user configures a `claude_proxy` agent and the configured provider API key variable is not available from the process environment or loaded `.env`
- **THEN** the command succeeds only if the configuration is valid and prints a warning naming the missing variable and how to set it

#### Scenario: Activate reports missing proxy key
- **WHEN** `agentweave activate` processes a configured `claude_proxy` agent whose required provider API key variable is missing
- **THEN** the activation output includes a readiness warning or error for that agent and emits a structured diagnostic event

#### Scenario: Switch and direct run keep failing early
- **WHEN** the user runs `agentweave switch <agent>` or `agentweave run --agent <agent>` for a proxy agent with a missing provider API key variable
- **THEN** the command exits before launching the provider proxy command and prints an actionable error naming the missing variable

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
- **WHEN** a setup, activation, sync, or registration step fails but the command continues
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

### Requirement: Activation readiness summary
The system SHALL summarize readiness after activation so users can see whether configured agents are immediately usable.

#### Scenario: Activate prints agent readiness table
- **WHEN** `agentweave activate` completes configuration steps
- **THEN** it prints a compact readiness summary for each configured agent covering runner type, CLI availability, required env vars, context file status, and overall readiness

#### Scenario: Activate emits diagnostics for degraded readiness
- **WHEN** one or more readiness checks warn or fail during activation
- **THEN** the system emits structured diagnostic events and provides remediation hints in the CLI output
