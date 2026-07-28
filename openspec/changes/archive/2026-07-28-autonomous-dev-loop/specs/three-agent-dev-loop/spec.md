## ADDED Requirements

### Requirement: Dev hub on port 8001 with its own database

The AgentWeave deployment SHALL support running a second Hub instance on port 8001 with its own database volume, separate from any interactive Hub instance. The dev Hub SHALL be configurable via environment variables (`AW_PORT`, `DATABASE_URL`) and SHALL start cleanly with its own healthcheck endpoint.

#### Scenario: Dev hub starts on port 8001

- **WHEN** the dev hub is started with `AW_PORT=8001` and a dedicated database path
- **THEN** the Hub SHALL respond on port 8001 with a passing healthcheck
- **AND** the Hub SHALL use its own database file that is independent of the interactive Hub's database

### Requirement: Per-agent git worktree with its own transport configuration

Each agent that participates in the dev loop SHALL have its own git worktree on a long-lived agent branch (`agent/<agent>`) with its own `.agentweave/transport.json` pointing at the dev Hub on port 8001.

#### Scenario: Each agent has its own worktree

- **WHEN** the dev loop is stood up for opencode, kimi, and codex
- **THEN** three worktrees SHALL exist, each on its own `agent/<agent>` branch
- **AND** each worktree's transport configuration SHALL target the dev Hub

#### Scenario: Agents never push to main

- **WHEN** an agent commits work in its worktree
- **THEN** the agent SHALL push only to `feature/<topic>` branches
- **AND** the agent SHALL NEVER push to `main` or to its own long-lived agent branch without explicit user instruction

### Requirement: Each agent has the autonomous_dev role assigned

Each agent that participates in the dev loop SHALL have the `autonomous_dev` role assigned in the dev Hub's session configuration. The role guide SHALL describe the wakeup workflow, the research-mode flow, the ground rules, the commit conventions, and the context-pressure response.

#### Scenario: Autonomous_dev role is assigned

- **WHEN** an agent joins the dev Hub
- **THEN** its role configuration SHALL include `autonomous_dev` alongside any domain roles the user has assigned

#### Scenario: Domain roles are invokable on demand

- **WHEN** an autonomous agent decides it needs a domain-specific methodology lens
- **THEN** the agent SHALL be able to invoke that role via the existing skills mechanism without requiring a session restart

### Requirement: Each agent has a long-lived CLI session

Each agent in the dev loop SHALL have a long-lived CLI session whose session ID is stable across job fires. Jobs that wake the agent SHALL use `session_mode=resume` so context accumulates across wakes.

#### Scenario: Session ID is stable per agent

- **WHEN** the same agent is woken by two scheduled jobs an hour apart
- **THEN** the second wake SHALL resume the same session ID as the first
- **AND** the agent SHALL have access to the conversation history from the first wake

### Requirement: Kickoff message is delivered on every wake

Every scheduled job that wakes an agent in the dev loop SHALL deliver a kickoff message whose body is generated from a shared template. The kickoff message SHALL encode the wakeup workflow, the collaboration rules, the ground rules, and the end-of-session checklist.

#### Scenario: Kickoff template is shared

- **WHEN** a wakeup job fires for any agent in the dev loop
- **THEN** the message body SHALL be generated from the shared kickoff template
- **AND** the message SHALL be delivered as the first user turn of the wake session

### Requirement: Scheduled jobs coordinate the three agents

The dev loop SHALL schedule jobs on a staggered cron so that the three agents do not all wake at the same minute.

#### Scenario: Jobs are staggered

- **WHEN** the dev loop is operational
- **THEN** the three agents' primary wake jobs SHALL fire on different minutes of the hour
- **AND** no two agents SHALL wake in the same minute by default

### Requirement: Pause and resume the loop trivially

The dev loop SHALL support a single command to pause all scheduled jobs for the night and a single command per job to resume them. There SHALL be no separate "sleep mode" state.

#### Scenario: Pause all jobs

- **WHEN** the user runs `aw jobs disable --all` against the dev Hub
- **THEN** all jobs targeting the three agents SHALL become disabled
- **AND** no agent SHALL be woken by a scheduled job until re-enabled

#### Scenario: Resume specific job

- **WHEN** the user runs `aw jobs enable <job-name>` against the dev Hub
- **THEN** that specific job SHALL become enabled and SHALL fire on its next scheduled tick
- **AND** other jobs SHALL remain in their previous state

### Requirement: Agents coordinate through Hub tasks and Hub messages

The three agents SHALL coordinate their work through the Hub task board and the Hub message bus.

#### Scenario: Work is claimed by task assignment

- **WHEN** an agent decides to work on a topic
- **THEN** it SHALL create or claim a Hub task for that work
- **AND** it SHALL signal the claim by updating the task's assignee and status

#### Scenario: Topics are proposed via blocking question

- **WHEN** an agent finishes research mode with two to four candidate topics
- **THEN** it SHALL post a blocking multiple-choice Hub question to the user with the candidates
- **AND** it SHALL NOT proceed until the user answers

### Requirement: Two-of-three consensus with third-agent tie-break

When the three agents disagree on a research direction, a code-review resolution, or an architecture choice, two agreeing agents SHALL decide. If the three agents form three different positions, the third agent SHALL cast the deciding vote. If the tie-breaker disagrees with both sides, the dispute SHALL be escalated to the user via a Hub question.

#### Scenario: Two-of-three agreement decides

- **WHEN** two agents agree on a direction and the third disagrees
- **THEN** the two agreeing agents SHALL proceed and the third SHALL defer

#### Scenario: Third agent tie-breaks

- **WHEN** the three agents form three different positions on a question
- **THEN** the agent that is not part of the dispute SHALL cast the deciding vote
- **AND** the dispute SHALL be resolved without user involvement

#### Scenario: Tie-breaker failure escalates to user

- **WHEN** the third agent also disagrees with both sides
- **THEN** the dispute SHALL be escalated to the user via a blocking Hub question with all three positions stated

### Requirement: Strict peer review on every feature branch

Every `feature/<topic>` branch SHALL require a peer-review task in the Hub before the lead agent marks it ready for the human to merge. The reviewer SHALL be deterministically assigned to an agent that did not author the branch.

#### Scenario: Reviewer assignment excludes the author

- **WHEN** a feature branch is pushed by one agent
- **THEN** the peer-review task SHALL be assigned to one of the other two agents
- **AND** the assignment SHALL rotate across the two eligible agents to avoid the same agent always reviewing

#### Scenario: Approval surfaces the branch to the user

- **WHEN** the reviewer approves the peer-review task
- **THEN** the lead agent SHALL mark the implementation task as ready for human merge
- **AND** the branch SHALL be visible on the dev Hub UI as ready for the user to review and merge

### Requirement: Idle behaviour is research, then question to the user

When an agent wakes with no assigned task, no claimable pending task, and no inbox question to answer, the agent SHALL enter research mode.

#### Scenario: Idle agent enters research mode

- **WHEN** an agent wakes with nothing to do
- **THEN** the agent SHALL NOT idle
- **AND** the agent SHALL enter research mode and produce candidate topics

#### Scenario: Research mode reads the spec folder

- **WHEN** an agent enters research mode
- **THEN** it SHALL read `openspec/changes/*` for active proposals
- **AND** it SHALL read `openspec/specs/*` for shipped requirements
- **AND** it SHALL read `ROADMAP.md` for the long-term plan

#### Scenario: Research mode produces candidate topics

- **WHEN** research mode completes
- **THEN** the agent SHALL post two to four candidate topics as a blocking multiple-choice Hub question
- **AND** the question SHALL include title, motivation, effort, suggested lead, suggested helpers, and risks per candidate

### Requirement: Deep dive creates an OpenSpec change and Hub tasks

When the user picks a research topic, the lead agent SHALL create the OpenSpec change folder, SHALL create a `feature/<topic>` branch, and SHALL create one Hub task per `tasks.md` item.

#### Scenario: Lead agent creates change folder and branch

- **WHEN** the user picks a research topic
- **THEN** the lead agent SHALL create `openspec/changes/<topic>/` with proposal, design, and tasks artefacts
- **AND** the lead agent SHALL create a `feature/<topic>` branch forked from `agent/<lead>`

#### Scenario: Supporting tasks are claimable

- **WHEN** the lead agent creates Hub tasks for the topic
- **THEN** supporting tasks SHALL be assignable to any of the other two agents
- **AND** supporting agents SHALL be notified via Hub messages

### Requirement: User can inject topics and override decisions via Hub messages

The user SHALL be able to inject a topic directly into the dev loop via a Hub message to any of the three agents, bypassing the research→question flow. The user SHALL also be able to override an agent's decision by sending a Hub message to that agent.

#### Scenario: User-injected topic is honoured

- **WHEN** the user sends a Hub message to an agent describing a topic
- **THEN** the agent SHALL treat that message as the chosen research direction on its next wake
- **AND** the agent SHALL proceed into deep-dive mode without requiring the user to pick from the research candidates

#### Scenario: User override is honoured

- **WHEN** the user sends a Hub message to an agent overriding a decision the agent has made
- **THEN** the agent SHALL treat the override as authoritative on its next wake
- **AND** the agent SHALL NOT re-debate the overridden decision

### Requirement: Operator runbook exists for standing up the loop

The AgentWeave documentation SHALL include a runbook that describes, in order: standing up the dev Hub on port 8001, creating the three per-agent worktrees, registering the three agents, scheduling the kickoff jobs, observing one day, and pausing/resuming the loop. The runbook SHALL include the red-flag interventions the user should watch for.

#### Scenario: Runbook exists

- **WHEN** the dev loop is operational
- **THEN** the runbook SHALL be available under `docs/guides/`
- **AND** the runbook SHALL include the standup, daily operation, and pause/resume steps