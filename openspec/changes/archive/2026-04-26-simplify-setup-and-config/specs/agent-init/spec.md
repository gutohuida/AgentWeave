## MODIFIED Requirements

### Requirement: Init does not require agents flag
`agentweave init` SHALL NOT require the `--agents` flag. If `--agents` is provided, CLI SHALL print a deprecation warning and continue (for one release cycle). The canonical way to define agents is `agentweave.yml`, populated after init.

#### Scenario: Init without --agents flag
- **WHEN** user runs `agentweave init --project "My App"` with no `--agents` flag
- **THEN** CLI creates a valid session with only the principal agent (default: `claude`)
- **THEN** CLI creates `agentweave.yml` with the principal agent pre-populated
- **THEN** CLI exits successfully with no error

#### Scenario: Init with deprecated --agents flag
- **WHEN** user runs `agentweave init --agents claude,kimi`
- **THEN** CLI prints "Warning: --agents is deprecated. Define agents in agentweave.yml instead."
- **THEN** CLI continues and creates the session with those agents for backward compatibility

#### Scenario: Init in project with existing session
- **WHEN** user runs `agentweave init` in a directory that already has `.agentweave/session.json`
- **THEN** CLI generates `agentweave.yml` from existing session state
- **THEN** CLI does NOT overwrite session.json
- **THEN** CLI prints "Existing session detected. Generated agentweave.yml from current configuration."
