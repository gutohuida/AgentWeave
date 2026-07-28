## ADDED Requirements

### Requirement: create_job MCP tool
The system SHALL expose a `create_job` MCP tool in both the CLI MCP server and the Hub MCP server. The tool SHALL accept `name`, `agent`, `message`, `cron`, and `session_mode` parameters. `session_mode` SHALL default to `"new"`. The tool SHALL return the created job's `id`.

#### Scenario: Agent creates a recurring job
- **WHEN** an agent calls `create_job(name="Standup", agent="pm", message="Generate standup", cron="0 9 * * 1-5", session_mode="resume")`
- **THEN** the job is stored in the active transport backend and the job ID is returned

#### Scenario: Invalid cron rejected via MCP
- **WHEN** an agent calls `create_job` with an invalid cron string
- **THEN** the tool returns an error string describing the cron format issue

### Requirement: list_jobs MCP tool
The system SHALL expose a `list_jobs` MCP tool that returns all jobs, optionally filtered by `agent` parameter. Each entry SHALL include id, name, agent, cron, enabled, last_run, next_run, run_count.

#### Scenario: List jobs for specific agent
- **WHEN** agent calls `list_jobs(agent="project-manager")`
- **THEN** only jobs targeting `project-manager` are returned

#### Scenario: List all jobs
- **WHEN** agent calls `list_jobs()` with no filter
- **THEN** all jobs across all agents are returned

### Requirement: get_job MCP tool
The system SHALL expose a `get_job(job_id)` tool returning full job details including the last 10 run history entries.

#### Scenario: Get job with history
- **WHEN** agent calls `get_job("job-abc123")`
- **THEN** full job definition plus last 10 JobRun entries are returned

### Requirement: delete_job MCP tool
The system SHALL expose a `delete_job(job_id)` tool that permanently removes the job and its history. The tool SHALL return a success/failure message.

#### Scenario: Agent deletes a job
- **WHEN** agent calls `delete_job("job-abc123")`
- **THEN** the job is removed from storage and `"deleted"` is returned

### Requirement: toggle_job MCP tool
The system SHALL expose a `toggle_job(job_id, enabled)` tool that enables or disables a job without deleting it.

#### Scenario: Agent pauses a job
- **WHEN** agent calls `toggle_job("job-abc123", enabled=False)`
- **THEN** the job's enabled field is set to false and the scheduler stops firing it

### Requirement: run_job MCP tool
The system SHALL expose a `run_job(job_id)` tool that fires the job immediately regardless of its cron schedule. The tool SHALL record a JobRun entry with `trigger: "manual"`.

#### Scenario: Agent triggers immediate execution
- **WHEN** agent calls `run_job("job-abc123")`
- **THEN** the job's message is sent to the target agent and a JobRun with `trigger: manual` is recorded

### Requirement: MCP tool routing by transport
Both the CLI MCP server and the Hub MCP server SHALL expose identical tool signatures. The CLI MCP server SHALL route through the active transport (`LocalTransport.create_job()`, `HttpTransport.create_job()`, etc.). The Hub MCP server SHALL call Hub internal functions directly.

#### Scenario: CLI MCP routes to local storage
- **WHEN** CLI MCP `create_job` is called with local transport active
- **THEN** the job is written to `.agentweave/jobs/<id>.json`

#### Scenario: CLI MCP routes to Hub
- **WHEN** CLI MCP `create_job` is called with http transport active
- **THEN** the job is created via POST /api/v1/jobs on the Hub
