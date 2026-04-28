# MCP Tools Reference

These tools are available to agents in **local MCP mode** (`agentweave-mcp`) and **Hub MCP mode** (`python -m hub.mcp_server`). Some tools are transport-specific as noted below.

## Messaging

### `send_message(from, to, subject, content)`

Send a message to another agent.

### `get_inbox(agent)`

Read unread messages for the specified agent. Messages are automatically archived after being returned — no need to call `mark_read()` separately.

### `mark_read(message_id)`

Archive a message manually. Usually not needed since `get_inbox` auto-marks messages as read.

## Tasks

### `list_tasks(agent?)`

List active tasks. Optionally filter by assignee.

### `get_task(task_id)`

Get full task details including requirements, acceptance criteria, and deliverables.

### `update_task(task_id, status)`

Update task status. Valid statuses: `pending`, `assigned`, `in_progress`, `completed`, `under_review`, `approved`, `revision_needed`, `rejected`.

### `create_task(title, ...)`

Create and assign a new task. Supports description, assignee, priority, requirements, and acceptance criteria.

## Session

### `get_status()`

Get a session-wide summary plus task counts by status and assignee.

### `list_agents()`

List all agents in the session with their roles and runners.

**Returns:** Array of agents with `name`, `session_role`, `runner`, `dev_roles`, and `is_principal` fields.

### `save_checkpoint(agent, session_intent, files_modified, decisions, next_steps, ...)` (local MCP only)

Save a context checkpoint before handoffs or session end. Writes to `.agentweave/shared/checkpoints/<agent>-<timestamp>.md`.

**Parameters:**
- `agent` — Your agent name
- `session_intent` — What this session was trying to accomplish
- `files_modified` — List of files changed with descriptions
- `decisions` — Decisions made with rationale
- `next_steps` — Ordered list of actions for next session
- `reason` — Why checkpoint is being written (token_threshold, phase_complete, pre_handoff, pre_sleep, manual)
- `blockers` — Optional unresolved blockers
- `verification_commands` — Optional shell commands to verify state

## Human Interaction (Hub only)

### `ask_user(from_agent, question)`

Post a question to the human. Returns a question ID.

### `get_answer(question_id)`

Check if the human has answered the question.

### `register_session(from_agent, session_id)`

Register a session ID for a pilot agent. This enables the Hub to track which session an agent is using.

**Parameters:**
- `from_agent` — Your agent name
- `session_id` — The session ID to register

**Returns:** Object with `success` boolean and `launch_command` string.

## Agent Configuration (Hub only)

### `get_agent_config(agent)`

Get configuration for a specific agent including runner type, base URL, and API key environment variable name. Useful for orchestrators that need to understand proxy agent setup.

**Returns:** Object with `runner`, `base_url`, `api_key_var`, and `pilot` fields.

## Self-Registration

Requires Hub/HTTP transport. In local MCP mode these tools return an error unless HTTP transport is active; in Hub MCP mode they call the Hub REST API directly.

### `register_agent(name, contact_mode, ...)`

Register or re-register an agent. `contact_mode` must be `poll`, `mcp-push`, or `watchdog-spawn`.

### `update_agent_config(name, ...)`

Partially update a self-registered agent's configuration, contact mode, MCP endpoint, or spawn command.

### `get_context(role)`

Return the markdown role guide for a role such as `backend_dev`.

### `heartbeat(agent)`

Send a liveness heartbeat for an agent.

## Jobs

AI Jobs allow scheduling recurring tasks for agents using cron expressions. Local transport stores jobs under `.agentweave/jobs/`; HTTP transport stores them in the Hub database and exposes them in the dashboard.

### `create_job(name, agent, message, cron, session_mode?)`

Create a new scheduled job.

**Parameters:**
- `name` — Human-readable job name
- `agent` — Target agent name
- `message` — Message/prompt sent to the agent
- `cron` — Cron expression for scheduling (e.g., `"0 9 * * 1-5"`)
- `session_mode` — `"new"` (default) or `"resume"`

**Returns:** Object with `success` boolean, `job_id`, and `message`.

### `list_jobs(agent?)`

List all jobs, optionally filtered by agent.

**Returns:** Array of job objects with `id`, `name`, `agent`, `cron`, `enabled`, `next_run`, etc.

### `get_job(job_id)`

Get detailed information about a job including run history.

**Returns:** Job object with `history` array of recent runs.

### `toggle_job(job_id, enabled)`

Enable or disable a job.

**Parameters:**
- `job_id` — Job ID to update
- `enabled` — `true` to enable, `false` to disable

### `delete_job(job_id)`

Delete a job and its history.

### `run_job(job_id)`

Manually trigger a job to run immediately, regardless of schedule.

See [AI Jobs Guide](../guides/ai-jobs.md) for more details.
