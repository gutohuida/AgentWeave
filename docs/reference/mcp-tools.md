# MCP Tools Reference

These tools are available to agents in both **local MCP mode** and **Hub MCP mode**.

## Messaging

### `send_message(from, to, subject, content)`

Send a message to another agent.

### `get_inbox(agent)`

Read unread messages for the specified agent.

### `mark_read(message_id)`

Archive a message after processing.

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

### `save_checkpoint(agent, session_intent, files_modified, decisions, next_steps, ...)` (CLI only)

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

## Agent Configuration (Hub only)

### `get_agent_config(agent)`

Get configuration for a specific agent including runner type, base URL, and API key environment variable name. Useful for orchestrators that need to understand proxy agent setup.

**Returns:** Object with `runner`, `base_url`, and `api_key_var` fields.
