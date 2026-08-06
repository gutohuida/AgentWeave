## MODIFIED Requirements

### Requirement: Project operating profile generation
The system SHALL generate a concise project operating profile from Hub-owned project, agent, runner,
and charter records. It MUST NOT depend on `agentweave.yml` or on synced session state, neither of
which exists in a Hub-owned project.

The profile SHALL name every agent registered in the project, so that an agent can address a peer
without guessing. For each agent it SHALL state that agent's name, its bound runner's CLI, and its
configured model, and SHALL mark which entry is the reading agent itself. Environment variables SHALL
be identified by name only, never by value.

Sections describing configuration the Hub does not hold SHALL be omitted rather than rendered empty
or populated with invented defaults.

#### Scenario: Profile names the real roster
- **WHEN** generated context is built for an agent in a project containing other agents
- **THEN** the profile lists every registered agent by name with its runner CLI and configured model
- **AND** marks the reading agent's own entry

#### Scenario: Profile does not depend on a synced session
- **WHEN** generated context is built for a project that has never synced session state
- **THEN** the profile is still complete, sourced from the Hub's own project, agent, and runner records
- **AND** does not report the project session as missing

#### Scenario: Secrets are never included
- **WHEN** an agent's runner declares environment variables
- **THEN** the profile includes their names only
- **AND** includes no value

#### Scenario: Absent configuration is omitted
- **WHEN** the Hub holds no quality-gate or scheduled-job configuration for a project
- **THEN** generated context omits those sections entirely
- **AND** does not render an empty or placeholder section in their place

#### Scenario: Profile includes quality gates when configured
- **WHEN** the Hub holds quality-gate configuration for the project
- **THEN** generated context includes actionable instructions for docs threshold, docs path, review
  requirement, echo-chamber guard, attribution tagging, and dependency checking

---

### Requirement: Agent context onboarding API
The Hub/MCP interface SHALL provide `get_agent_context(agent)` for retrieving runtime context by
agent name. Whether an agent is known SHALL be determined by whether the Hub has a record of it, and
by nothing else.

An agent the Hub knows SHALL receive full runtime context. The system MUST NOT instruct a known agent
to withhold work, to refrain from modifying files, to refrain from claiming tasks, or to wait for
another agent to assign it work. An agent the operator created and addressed is an agent the operator
intends to act.

Generated context MUST NOT refer to `agentweave.yml`, to an agent being "declared", or to a
"principal", unless a real registered agent holds that position.

#### Scenario: A known agent receives runtime context
- **WHEN** `get_agent_context(agent)` is called for an agent the Hub has a record of
- **THEN** the response returns full runtime context including the project profile, the real agent
  roster, project instructions, bound charter guidance or a clear no-charter notice, and communication
  guidance
- **AND** contains no instruction to stand by or withhold work

#### Scenario: A known agent is not told to wait for a principal
- **WHEN** generated context is built for any agent the Hub has a record of
- **THEN** it contains no direction to await assignment before acting
- **AND** names no recipient that is not a registered agent of that project

#### Scenario: Unknown agent receives registration guidance
- **WHEN** `get_agent_context(agent)` is called for an agent the Hub has no record of
- **THEN** the response explains how to register with AgentWeave and does not provide work-taking
  instructions beyond read-only orientation

#### Scenario: Agent context response exposes machine-readable status
- **WHEN** `get_agent_context(agent)` returns successfully
- **THEN** the response includes machine-readable fields for agent name, known status, registered
  status, charter identity, missing context inputs, and markdown context content
