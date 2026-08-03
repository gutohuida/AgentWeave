## MODIFIED Requirements

### Requirement: Layered project and role context
The system SHALL layer stable role guidance, generated project facts, long-lived project context, project-wide instructions, and live session state without duplicating stale information across files.

#### Scenario: Role files remain stable contracts
- **WHEN** role markdown files are copied or generated
- **THEN** they describe role scope, responsibilities, boundaries, handoff rules, quality behavior, definition of done, and escalation paths without embedding a full copy of `agentweave.yml`

#### Scenario: Placeholder project context is not silently injected
- **WHEN** `.agentweave/ai_context.md` contains known untouched template placeholders
- **THEN** generated context omits the placeholder content or includes a clear missing-context warning instead of presenting the placeholder as project facts

#### Scenario: Live shared context is prompt-level for Hub-triggered runs
- **WHEN** the Hub triggers an agent from a peer message and `.agentweave/shared/context.md` is non-empty
- **THEN** the system prepends the shared context to the prompt as current session focus without requiring regeneration of `.agentweave/context/<agent>.md`
