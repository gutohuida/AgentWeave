## MODIFIED Requirements

### Requirement: Persistent span records
The Hub SHALL persist span records that describe ordered units of work inside a trace.

#### Scenario: Message span is recorded
- **WHEN** a task-linked message is created
- **THEN** the Hub records a message span linked to the task trace

#### Scenario: Agent run span is recorded
- **WHEN** an agent is triggered through the Hub for a traced message or session
- **THEN** the Hub records an agent-run span linked to the resolved trace
