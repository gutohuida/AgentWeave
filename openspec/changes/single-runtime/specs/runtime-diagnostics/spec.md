## MODIFIED Requirements

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
