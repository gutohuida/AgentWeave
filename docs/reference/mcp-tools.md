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

## Human Interaction (Hub only)

### `ask_user(from_agent, question)`

Post a question to the human. Returns a question ID.

### `get_answer(question_id)`

Check if the human has answered the question.
