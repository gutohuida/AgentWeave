## ADDED Requirements

### Requirement: Persistent trace records
The Hub SHALL persist trace records that group related multi-agent activity under a system-assigned trace identifier.

#### Scenario: Task trace is created
- **WHEN** a task-related activity is created without an existing trace
- **THEN** the Hub creates a trace with root type `task` and root ID equal to the task ID

#### Scenario: Trace identifiers are system assigned
- **WHEN** an agent sends a message or updates a task
- **THEN** the Hub assigns or resolves the trace ID instead of requiring the agent to provide one

### Requirement: Persistent span records
The Hub SHALL persist span records that describe ordered units of work inside a trace.

#### Scenario: Message span is recorded
- **WHEN** a task-linked message is created
- **THEN** the Hub records a message span linked to the task trace

#### Scenario: Agent run span is recorded
- **WHEN** an agent is triggered through the Hub or watchdog for a traced message or session
- **THEN** the Hub records an agent-run span linked to the resolved trace

### Requirement: Trace correlation
The Hub SHALL correlate activity to traces using existing AgentWeave identifiers including task ID, session ID, message ID, and job run ID.

#### Scenario: Message joins task trace
- **WHEN** a message is created with a `task_id`
- **THEN** the message is linked to the trace rooted at that task

#### Scenario: Agent output joins session trace
- **WHEN** agent output is received with a `session_id` and no task trace can be resolved
- **THEN** the output is linked to a trace rooted at that session

#### Scenario: Job run joins job trace
- **WHEN** a scheduled AI job fires
- **THEN** job-run activity is linked to a trace rooted at that job run

### Requirement: Trace list API
The Hub SHALL expose an authenticated API that lists traces for the current project.

#### Scenario: User lists traces
- **WHEN** an authenticated user requests the trace list
- **THEN** the Hub returns traces for only the authenticated project

#### Scenario: User filters traces
- **WHEN** an authenticated user filters traces by root type, status, agent, or search text
- **THEN** the Hub returns only traces matching those filters

### Requirement: Trace detail API
The Hub SHALL expose an authenticated API that returns one trace with its spans and related source records.

#### Scenario: User opens trace detail
- **WHEN** an authenticated user requests a trace by ID
- **THEN** the Hub returns the trace, ordered spans, related events, and source references for the authenticated project

#### Scenario: User requests another project's trace
- **WHEN** an authenticated user requests a trace outside their project
- **THEN** the Hub denies access or returns not found

### Requirement: Timeline UI
The Hub UI SHALL render trace timelines that show correlated activity in chronological order.

#### Scenario: User views a trace
- **WHEN** a user opens a trace detail page
- **THEN** the UI displays the trace summary and chronological timeline of spans and related activity

#### Scenario: User navigates from source record
- **WHEN** a user views a task, session, job run, log row, or agent activity that has trace context
- **THEN** the UI provides a way to open the related trace

### Requirement: Agent traceability instructions
Generated AgentWeave instructions SHALL explain how agents preserve trace continuity without manually creating trace identifiers.

#### Scenario: Agent reads generated context
- **WHEN** AgentWeave generates AI context or collaboration protocol instructions
- **THEN** the instructions tell agents to pass task IDs for task-related messages, update task status at meaningful boundaries, use Hub/MCP tools when available, include verification commands, and not invent trace or span IDs

#### Scenario: Agent follows task handoff flow
- **WHEN** an agent delegates or completes task-related work using the instructed handoff format
- **THEN** the message remains linkable to the same task trace through the provided task ID
