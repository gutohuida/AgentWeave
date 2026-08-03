## MODIFIED Requirements

### Requirement: Layered project and role context
The system SHALL layer stable charter guidance, generated project facts, long-lived project context, project-wide instructions, and live session state without duplicating stale information across files.

#### Scenario: Charter content remains a stable contract
- **WHEN** a charter is authored or edited through the Hub UI
- **THEN** it describes agent scope, responsibilities, boundaries, handoff rules, quality behavior, definition of done, and escalation paths without embedding a full copy of project instructions

#### Scenario: Placeholder project context is not silently injected
- **WHEN** `.agentweave/ai_context.md` contains known untouched template placeholders
- **THEN** generated context omits the placeholder content or includes a clear missing-context warning instead of presenting the placeholder as project facts

#### Scenario: Live shared context is prompt-level for Hub-triggered runs
- **WHEN** the Hub triggers an agent from a peer message and `.agentweave/shared/context.md` is non-empty
- **THEN** the system prepends the shared context to the prompt as current session focus without requiring regeneration of `.agentweave/context/<agent>.md`

---

### Requirement: Role context lookup compatibility
The system SHALL preserve `get_context(charter)` as a direct charter-content lookup while making `get_agent_context(agent)` the preferred onboarding/runtime context API.

#### Scenario: Existing charter lookup still works
- **WHEN** an agent calls `get_context(charter)` with a valid charter identifier
- **THEN** the system returns that charter's content compatible with existing clients

#### Scenario: Charter lookup directs agents to richer context
- **WHEN** `get_context(charter)` returns charter content
- **THEN** the returned content or metadata indicates that `get_agent_context(agent)` should be used for full project and onboarding context when the caller knows its agent name
