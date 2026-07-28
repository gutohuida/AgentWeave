## ADDED Requirements

### Requirement: Agent can retrieve role guide content over MCP
The system SHALL provide a `get_context(role)` MCP tool that returns the role guide markdown content as a string. This allows self-registered agents to bootstrap their instructions without filesystem access.

#### Scenario: Valid role returns content
- **WHEN** an agent calls `get_context(role="worker")`
- **THEN** the system returns `{ content: "<full markdown content of the worker role guide>" }`

#### Scenario: Unknown role returns error
- **WHEN** an agent calls `get_context(role="nonexistent")`
- **THEN** the system returns `{ error: "Role 'nonexistent' not found" }`

#### Scenario: Context returned at registration
- **WHEN** `register_agent()` succeeds
- **THEN** the response includes the `context` field containing the assigned role's guide content
- **AND** the agent does not need to call `get_context()` separately on first startup

#### Scenario: Agent re-fetches context after compaction
- **WHEN** an agent loses its context due to `/compact` or restart
- **AND** the agent calls `register_agent()` again
- **THEN** the context field in the response contains the current role guide content
- **AND** the agent can resume normal operation without any other recovery steps

### Requirement: Context content is the role template markdown
The content returned by `get_context()` SHALL be the same role guide markdown that would be written to `.agentweave/roles/<role>.md` for configured agents — loaded from `templates/roles/<role>.md` at call time.

#### Scenario: Content matches role template
- **WHEN** `get_context(role="worker")` is called
- **THEN** the returned content matches the contents of `src/agentweave/templates/roles/worker.md`
