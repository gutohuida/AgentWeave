## ADDED Requirements

### Requirement: agentweave.yml accepts runner: opencode
The system SHALL accept `runner: opencode` as a valid value in an agent's configuration block in `agentweave.yml`, passing validation without error.

#### Scenario: Valid opencode runner with local model
- **WHEN** `agentweave.yml` contains an agent with `runner: opencode` and `model: ollama/qwen2.5-coder:7b`
- **THEN** `load_agentweave_yml()` SHALL return an `AgentConfig` with `runner="opencode"` and `model="ollama/qwen2.5-coder:7b"` without raising `ConfigValidationError`

#### Scenario: Valid opencode runner with cloud model
- **WHEN** `agentweave.yml` contains an agent with `runner: opencode` and `model: anthropic/claude-sonnet-4-5`
- **THEN** `load_agentweave_yml()` SHALL return an `AgentConfig` with `runner="opencode"` and `model="anthropic/claude-sonnet-4-5"` without raising `ConfigValidationError`

#### Scenario: Valid opencode runner without model (uses opencode default)
- **WHEN** `agentweave.yml` contains an agent with `runner: opencode` and no `model` field
- **THEN** `load_agentweave_yml()` SHALL return an `AgentConfig` with `runner="opencode"` and `model=None` without raising `ConfigValidationError`

---

### Requirement: agentweave.yml opencode agents support roles, env, yolo, pilot
The system SHALL accept the same optional fields for opencode agents as for all other runner types.

#### Scenario: opencode agent with roles and env
- **WHEN** `agentweave.yml` contains an opencode agent with `roles: [developer]` and `env: [SOME_VAR]`
- **THEN** `load_agentweave_yml()` SHALL return an `AgentConfig` with `roles=["developer"]` and `env=["SOME_VAR"]`

#### Scenario: opencode agent with pilot mode
- **WHEN** `agentweave.yml` contains an opencode agent with `pilot: true`
- **THEN** the agent SHALL be treated as pilot (watchdog skips auto-execution) identically to other runner types

---

### Requirement: generate_agentweave_yml serializes opencode agents correctly
The system SHALL serialize opencode agents back to `agentweave.yml` with the correct `runner: opencode` and `model` fields when `generate_agentweave_yml()` is called.

#### Scenario: Round-trip serialization preserves runner and model
- **WHEN** a session contains an opencode agent with `runner="opencode"` and `model="ollama/qwen2.5-coder:7b"`
- **THEN** the generated `agentweave.yml` SHALL contain `runner: opencode` and `model: ollama/qwen2.5-coder:7b` under that agent's key

---

### Requirement: agentweave init printed instructions include opencode example
When a user runs `agentweave init` and the session includes an opencode agent, the system SHALL print a reminder that `agentweave mcp-setup` will write `opencode.json`.

#### Scenario: Init output mentions opencode.json
- **WHEN** `agentweave init` completes with at least one opencode agent in the session
- **THEN** the printed instructions SHALL mention that `agentweave mcp-setup` configures `opencode.json`
