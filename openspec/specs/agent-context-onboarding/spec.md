# agent-context-onboarding Specification

## Purpose
Define generated model-facing context, project operating profiles, and Hub/MCP onboarding for declared, registered, and external agents so every agent starts work with complete, fresh, non-placeholder project context.

## Requirements
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

### Requirement: Project operating profile generation
The system SHALL generate a concise project operating profile from validated AgentWeave configuration and runtime state.

#### Scenario: Profile includes project and team facts
- **WHEN** generated context is built
- **THEN** the project operating profile includes project name, collaboration mode, principal agent, agents, runners, configured models, assigned roles, yolo markers, and safe environment variable names without secret values

#### Scenario: Profile includes quality gates
- **WHEN** `agentweave.yml` or session state contains `quality` settings
- **THEN** generated context includes actionable quality gate instructions for docs threshold, docs path, review requirement, echo-chamber guard, attribution tagging, and dependency checking

#### Scenario: Profile includes scheduled job summary
- **WHEN** `agentweave.yml` contains scheduled jobs
- **THEN** generated context includes a compact summary of job names, target agents, schedules, and enabled state without expanding full long prompts unless needed for the target agent

---

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

---

### Requirement: Role context lookup compatibility
The system SHALL preserve `get_context(charter)` as a direct charter-content lookup while making `get_agent_context(agent)` the preferred onboarding/runtime context API.

#### Scenario: Existing charter lookup still works
- **WHEN** an agent calls `get_context(charter)` with a valid charter identifier
- **THEN** the system returns that charter's content compatible with existing clients

#### Scenario: Charter lookup directs agents to richer context
- **WHEN** `get_context(charter)` returns charter content
- **THEN** the returned content or metadata indicates that `get_agent_context(agent)` should be used for full project and onboarding context when the caller knows its agent name

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
