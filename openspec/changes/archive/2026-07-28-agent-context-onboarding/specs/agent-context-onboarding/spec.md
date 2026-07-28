## ADDED Requirements

### Requirement: Canonical per-agent runtime context
The system SHALL treat `.agentweave/context/<agent>.md` as the canonical runtime context artifact for declared agents.

#### Scenario: Sync generates canonical context for each declared agent
- **WHEN** `agentweave sync-context` runs for a session with declared agents
- **THEN** the system writes `.agentweave/context/<agent>.md` for each synced agent with the agent's project operating profile, team context, quality gates, assigned role guides, project instructions, and project context when available

#### Scenario: Activate refreshes generated context
- **WHEN** `agentweave activate` reconciles `agentweave.yml` successfully
- **THEN** the system refreshes generated per-agent context so role, runner, project, and quality changes are reflected before agents are launched

#### Scenario: Runtime launch uses generated context where supported
- **WHEN** AgentWeave launches or recommends a launch command for a supported runner
- **THEN** the command injects `.agentweave/context/<agent>.md` using that runner's supported context mechanism

### Requirement: Project operating profile generation
The system SHALL generate a concise project operating profile from validated AgentWeave configuration and runtime state.

#### Scenario: Profile includes project and team facts
- **WHEN** generated context is built
- **THEN** the project operating profile includes project name, collaboration mode, principal agent, agents, runners, configured models, assigned roles, pilot/yolo markers, and safe environment variable names without secret values

#### Scenario: Profile includes quality gates
- **WHEN** `agentweave.yml` or session state contains `quality` settings
- **THEN** generated context includes actionable quality gate instructions for docs threshold, docs path, review requirement, echo-chamber guard, attribution tagging, and dependency checking

#### Scenario: Profile includes scheduled job summary
- **WHEN** `agentweave.yml` contains scheduled jobs
- **THEN** generated context includes a compact summary of job names, target agents, schedules, and enabled state without expanding full long prompts unless needed for the target agent

### Requirement: Layered project and role context
The system SHALL layer stable role guidance, generated project facts, long-lived project context, project-wide instructions, and live session state without duplicating stale information across files.

#### Scenario: Role files remain stable contracts
- **WHEN** role markdown files are copied or generated
- **THEN** they describe role scope, responsibilities, boundaries, handoff rules, quality behavior, definition of done, and escalation paths without embedding a full copy of `agentweave.yml`

#### Scenario: Placeholder project context is not silently injected
- **WHEN** `.agentweave/ai_context.md` contains known untouched template placeholders
- **THEN** generated context omits the placeholder content or includes a clear missing-context warning instead of presenting the placeholder as project facts

#### Scenario: Live shared context is prompt-level for watchdog triggers
- **WHEN** the watchdog triggers an agent from a Hub/direct message and `.agentweave/shared/context.md` is non-empty
- **THEN** the system prepends the shared context to the prompt as current session focus without requiring regeneration of `.agentweave/context/<agent>.md`

### Requirement: Agent context onboarding API
The Hub/MCP interface SHALL provide `get_agent_context(agent)` for retrieving full onboarding or runtime context by agent name.

#### Scenario: Declared agent receives runtime context
- **WHEN** `get_agent_context(agent)` is called for an agent declared in the active AgentWeave session
- **THEN** the response includes structured metadata indicating the agent is declared and returns the same canonical context content that would be generated for `.agentweave/context/<agent>.md`

#### Scenario: Registered undeclared agent receives provisional context
- **WHEN** `get_agent_context(agent)` is called for an agent registered with Hub but not declared in `agentweave.yml`
- **THEN** the response includes provisional onboarding context with project summary, communication rules, available roles, requested role guidance when present, and explicit restrictions against modifying files or claiming tasks until assigned

#### Scenario: Unknown agent receives registration guidance
- **WHEN** `get_agent_context(agent)` is called for an unknown agent
- **THEN** the response explains how to register with AgentWeave and does not provide work-taking instructions beyond read-only orientation

#### Scenario: Agent context response exposes machine-readable status
- **WHEN** `get_agent_context(agent)` returns successfully
- **THEN** the response includes machine-readable fields for agent name, known status, declared status, registered status, provisional status, roles, missing context inputs, and markdown context content

### Requirement: Role context lookup compatibility
The system SHALL preserve `get_context(role)` as a role-guide lookup while making `get_agent_context(agent)` the preferred onboarding/runtime context API.

#### Scenario: Existing role lookup still works
- **WHEN** an agent calls `get_context(role)` with a valid role id
- **THEN** the system returns role guidance compatible with existing clients

#### Scenario: Role lookup directs agents to richer context
- **WHEN** `get_context(role)` returns role content
- **THEN** the returned content or metadata indicates that `get_agent_context(agent)` should be used for full project and onboarding context when the caller knows its agent name

### Requirement: Context diagnostics
The system SHALL provide diagnostics that explain what context each agent receives and whether it is fresh enough to trust.

#### Scenario: Diagnostics list context inputs and outputs
- **WHEN** AgentWeave context diagnostics run
- **THEN** the output lists relevant source files, generated per-agent context files, root bootstrap files, and runner-specific injection mechanisms

#### Scenario: Diagnostics detect stale or incomplete generated context
- **WHEN** generated context is missing, older than relevant source files, or lacks required sections
- **THEN** diagnostics report the issue and suggest `agentweave sync-context` or `agentweave sync-context --force`

#### Scenario: Diagnostics flag placeholder project context
- **WHEN** `.agentweave/ai_context.md` still contains known template placeholders
- **THEN** diagnostics warn that project context is incomplete and identify the file to update
