## ADDED Requirements

### Requirement: runner_options is a valid agent config key
`runner_options` SHALL be added to `VALID_AGENT_CONFIG_KEYS` in `constants.py`. Its value SHALL be a dict of runner-specific options. Unknown keys SHALL be accepted without error (free-form).

#### Scenario: Valid agentweave.yml with runner_options
- **WHEN** `agentweave.yml` contains `runner_options: {memory: false}` under an agent
- **THEN** `agentweave activate` applies it without validation error

#### Scenario: runner_options absent
- **WHEN** an agent has no `runner_options` key
- **THEN** `session.get_runner_options(agent)` returns `{}`

---

### Requirement: Session exposes get_runner_options accessor
`session.get_runner_options(agent)` SHALL return the `runner_options` dict for the given agent, defaulting to `{}`.

#### Scenario: Options present
- **WHEN** agent config contains `runner_options: {memory: false}`
- **THEN** `get_runner_options("agent")` returns `{"memory": False}`

#### Scenario: Options absent
- **WHEN** agent has no `runner_options`
- **THEN** `get_runner_options("agent")` returns `{}`

---

### Requirement: sync_from_yaml applies runner_options
`session.sync_from_yaml()` SHALL read `runner_options` from `agentweave.yml` and persist it into the session's agent data.

#### Scenario: Sync applies runner_options
- **WHEN** `agentweave.yml` sets `runner_options: {memory: false}` and `agentweave activate` runs
- **THEN** `session.agents["codex"]["runner_options"]` equals `{"memory": false}`

---

### Requirement: Codex runner maps runner_options.memory to CLI flag
When building the Codex exec command, the watchdog SHALL append `-c memory_mode=disabled` if `runner_options.memory` is `false`.

#### Scenario: Memory disabled
- **WHEN** `runner_options.memory` is `false` for a Codex agent
- **THEN** the exec command includes `-c memory_mode=disabled`

#### Scenario: Memory enabled (default)
- **WHEN** `runner_options.memory` is `true` or absent
- **THEN** the exec command does NOT include `-c memory_mode=disabled`

---

### Requirement: runner_options is documented in agentweave.yml example
The generated `agentweave.yml` template SHALL include a commented-out `runner_options` block under the codex agent example showing `memory: true`.

#### Scenario: Init generates commented example
- **WHEN** `agentweave init` creates a new `agentweave.yml`
- **THEN** the file contains a commented example with `runner_options` under a codex agent entry
