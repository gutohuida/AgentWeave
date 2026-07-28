## ADDED Requirements

### Requirement: Idea exploration focuses on discovery before execution planning

The AW-Spec workflow SHALL provide an idea exploration skill that helps users investigate what they want to build, why it matters, which workflows or requirements are involved, what risks or unknowns exist, and which parts of the current codebase are relevant.

The idea exploration skill MUST NOT require AgentWeave session, role, team, or quality configuration loading as an initial step.

#### Scenario: User explores a new idea

- **WHEN** a user invokes `aw-spec-explore` with an idea or problem
- **THEN** the skill guides exploration of the problem space, requirements, workflows, risks, and relevant codebase context before discussing implementation ownership

#### Scenario: User explores in a project without AgentWeave session state

- **WHEN** a user invokes `aw-spec-explore` in a repository without `.agentweave/session.json`
- **THEN** the skill remains useful and does not fail or center the conversation on missing AgentWeave session state

### Requirement: Technical exploration plans how the work will be built

The AW-Spec workflow SHALL provide an `aw-spec-technical-explore` skill for technical discovery after idea exploration and before proposal generation.

The technical exploration skill SHALL investigate architecture, integration points, current technologies, framework choices, deployment model, testing strategy, implementation sequencing, and development flow.

#### Scenario: User explores technical implementation for an existing project

- **WHEN** a user invokes `aw-spec-technical-explore` in an existing project
- **THEN** the skill discovers existing architecture, stack, conventions, tests, and deployment patterns
- **AND** it treats decisions already made by the project as constraints unless there is a clear reason to revisit them

#### Scenario: User explores technical implementation for a new project

- **WHEN** a user invokes `aw-spec-technical-explore` for a new project or greenfield area
- **THEN** the skill helps compare and select technologies, frameworks, persistence, deployment, CI, and testing approach

### Requirement: Technical exploration includes AgentWeave execution strategy

The technical exploration skill SHALL evaluate which available AgentWeave agents and roles should participate in implementation, what each should own, how handoffs should be sequenced, and how the development cycle should flow.

If project quality settings exist, the skill SHALL integrate them into the proposed testing, review, documentation, and delegation strategy.

#### Scenario: Project has available AgentWeave agents

- **WHEN** technical exploration runs in a project with AgentWeave agent and role configuration
- **THEN** the skill maps relevant work areas to suitable agents or roles
- **AND** it identifies missing roles or sequencing constraints where they affect implementation

#### Scenario: Project has no available AgentWeave agent context

- **WHEN** technical exploration cannot find AgentWeave agent or role configuration
- **THEN** the skill recommends ideal roles from the technical scope without blocking exploration

### Requirement: Proposal generation uses prior exploration when available

The AW-Spec proposal skill SHALL look for prior idea and technical exploration artifacts when creating a change proposal.

When prior exploration artifacts are present, proposal generation MUST use them as source context for proposal, design, tasks, and team planning. If the current codebase conflicts with prior artifacts, proposal generation MUST surface the conflict instead of silently inventing a new plan.

#### Scenario: Discovery artifacts exist

- **WHEN** a user invokes `aw-spec-propose` for a topic with existing idea and technical discovery artifacts
- **THEN** the generated proposal, design, tasks, and team recommendations reflect the decisions and open questions captured in those artifacts

#### Scenario: Discovery artifacts are absent

- **WHEN** a user invokes `aw-spec-propose` without prior discovery artifacts
- **THEN** the skill still creates a proposal from the user's request using the existing quick-propose workflow

### Requirement: Documentation describes the expanded AW-Spec flow

The AgentWeave documentation SHALL describe the AW-Spec workflow as idea exploration, technical exploration, proposal generation, implementation, and archival.

Documentation SHALL explain when to use each stage and that both exploration stages are optional but recommended for unclear or complex work.

#### Scenario: User reads the AW-Spec guide

- **WHEN** a user reads the AW-Spec workflow documentation
- **THEN** they see `aw-spec-technical-explore` listed between `aw-spec-explore` and `aw-spec-propose`
- **AND** they understand the distinction between exploring what to build and exploring how to build it
