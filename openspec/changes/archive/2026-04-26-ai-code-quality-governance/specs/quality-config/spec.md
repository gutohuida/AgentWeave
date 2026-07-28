## ADDED Requirements

### Requirement: Quality config section in agentweave.yml
The system SHALL support a top-level `quality:` section in `agentweave.yml` with the following fields:
- `review_required` (bool, default: false) — gates task approval behind a review step
- `docs_path` (string, optional) — path for decision docs; omit for `.agentweave/code-docs/` (gitignored); set to commit alongside code
- `docs_threshold` (enum: `all` | `non_trivial` | `never`, default: `never`) — when implementing agents must produce a decision doc
- `echo_chamber_guard` (enum: `off` | `warn` | `enforce`, default: `off`) — prevents the same agent from implementing and reviewing the same task
- `attribution_tag` (bool, default: false) — requires implementing agents to list AI-generated files in the decision doc header
- `dependency_check` (bool, default: false) — signals to reviewing agents that all imports must be verified against the real package registry

#### Scenario: Valid quality config loads without error
- **WHEN** `agentweave.yml` contains a `quality:` section with valid field values
- **THEN** the system SHALL parse it into a `QualityConfig` dataclass with no validation error

#### Scenario: Missing quality section uses safe defaults
- **WHEN** `agentweave.yml` has no `quality:` section
- **THEN** the system SHALL use `QualityConfig` defaults (all governance features off) and continue normally

#### Scenario: Invalid docs_threshold value raises error
- **WHEN** `quality.docs_threshold` is set to a value not in `["all", "non_trivial", "never"]`
- **THEN** `agentweave activate` SHALL raise a `ConfigValidationError` with the valid values listed

#### Scenario: Invalid echo_chamber_guard value raises error
- **WHEN** `quality.echo_chamber_guard` is set to a value not in `["off", "warn", "enforce"]`
- **THEN** `agentweave activate` SHALL raise a `ConfigValidationError` with the valid values listed

### Requirement: Quality config serialized into session.json
The system SHALL include the `quality` section in the `session.json` payload so it is synced to the Hub via the existing session sync path.

#### Scenario: Quality config appears in synced session data
- **WHEN** `agentweave activate` runs with a `quality:` section present in `agentweave.yml`
- **THEN** `session.json` SHALL contain a `quality` key with all configured fields

#### Scenario: Hub receives quality config without new endpoint
- **WHEN** session.json is synced to the Hub via `POST /api/v1/session/sync`
- **THEN** `GET /api/v1/session/sync` SHALL return `data.quality` with the current quality settings

### Requirement: echo_chamber_guard degrades gracefully in single-agent sessions
The system SHALL degrade `enforce` to `warn` behavior when only one agent is active in the session, rather than blocking task routing entirely.

#### Scenario: Enforce with single agent warns instead of blocking
- **WHEN** `echo_chamber_guard: enforce` is set and only one agent exists in the session
- **THEN** the system SHALL log a warning noting the guard cannot be enforced and proceed with routing
