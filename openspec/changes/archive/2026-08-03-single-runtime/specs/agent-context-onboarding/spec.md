## MODIFIED Requirements

### Requirement: Canonical per-agent runtime context
The Hub SHALL build canonical runtime context for each configured agent and supply it to every run.
It MAY materialize that context inside a run workspace when a runner requires a file.

#### Scenario: Hub generates canonical context for each configured agent
- **WHEN** the Hub prepares a run for a configured agent
- **THEN** it builds context containing the agent's project operating profile, team context, quality gates, charter guidance, project instructions, and project context when available

#### Scenario: Run preparation uses current configuration
- **WHEN** agent, runner, project, charter, or quality configuration changes before a run
- **THEN** the next run receives context generated from the current Hub-owned configuration

#### Scenario: Runtime launch injects generated context
- **WHEN** the Hub launches a supported runner
- **THEN** it supplies canonical context using that runner's supported prompt or file mechanism

---

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

---

### Requirement: Context diagnostics
The system SHALL provide diagnostics that explain what context each agent receives and whether it is fresh enough to trust.

#### Scenario: Diagnostics list context inputs and outputs
- **WHEN** AgentWeave context diagnostics run
- **THEN** the output lists relevant source files, generated per-agent context files, root bootstrap files, and runner-specific injection mechanisms

#### Scenario: Diagnostics detect incomplete generated context
- **WHEN** generated context is missing required inputs or sections
- **THEN** diagnostics report the issue and identify the Hub-owned configuration that needs attention

#### Scenario: Diagnostics flag placeholder project context
- **WHEN** `.agentweave/ai_context.md` still contains known template placeholders
- **THEN** diagnostics warn that project context is incomplete and identify the file to update
