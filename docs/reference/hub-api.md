# Hub API Reference

The AgentWeave Hub exposes a REST API for messages, tasks, logs, agents, and human questions.

## Authentication

All endpoints require a Bearer token:

```bash
Authorization: Bearer aw_live_<your-key>
```

## Base URL

```
http://localhost:8000/api/v1
```

## Endpoints Overview

### Messages

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/messages` | Send a message |
| `GET` | `/messages` | List messages (with filters) |
| `PATCH` | `/messages/{id}/read` | Mark a message as read |

### Tasks

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/tasks` | Create a task |
| `GET` | `/tasks` | List tasks |
| `GET` | `/tasks/{id}` | Get task details |
| `PATCH` | `/tasks/{id}` | Update task |

### Agents

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/agents` | List all agents |
| `GET` | `/agents/configured` | List configured agents for project |
| `GET` | `/agents/{name}` | Get agent details |
| `POST` | `/agents/{name}/heartbeat` | Post agent heartbeat |
| `POST` | `/agents/{name}/output` | Post agent output log |
| `GET` | `/agents/{name}/output` | Get agent output log |
| `GET` | `/agents/{name}/timeline` | Get agent timeline events |
| `GET` | `/agents/{name}/chat` | Get agent chat history |
| `GET` | `/agents/{name}/chat/{session_id}` | Get specific chat session |
| `PUT` | `/agents/roles/config` | Update roles configuration |
| `GET` | `/agents/roles/config` | Get roles configuration |

### Logs

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/logs` | Push a structured log event |
| `GET` | `/logs` | Query event logs |

### Questions

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/questions` | Ask the human a question |
| `GET` | `/questions` | List questions |
| `GET` | `/questions/{id}` | Get question details |
| `PATCH` | `/questions/{id}` | Update question (e.g., answer) |

### Session Sync

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/session/sync` | Sync session data to Hub |
| `GET` | `/session/sync` | Get synced session data |

### Jobs

AI Jobs endpoints for scheduled recurring agent tasks.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/jobs` | List all jobs |
| `POST` | `/jobs` | Create a new job |
| `GET` | `/jobs/{id}` | Get job details and history |
| `PATCH` | `/jobs/{id}` | Update job (enable/disable, modify settings) |
| `DELETE` | `/jobs/{id}` | Delete a job |
| `POST` | `/jobs/{id}/run` | Manually trigger a job |
| `POST` | `/jobs/{id}/toggle` | Toggle job enabled state |

**Job Object:**
```json
{
  "id": "job-abc123",
  "name": "Daily Report",
  "agent": "claude",
  "message": "Generate daily summary",
  "cron": "0 9 * * 1-5",
  "session_mode": "new",
  "enabled": true,
  "created_at": "2026-04-01T09:00:00Z",
  "last_run": "2026-04-12T09:00:00Z",
  "next_run": "2026-04-13T09:00:00Z",
  "run_count": 10,
  "history": [...]
}
```

See [AI Jobs Guide](../guides/ai-jobs.md) for detailed usage.

### Status

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | Session-wide summary and task counts |

### Setup

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/setup/token` | Get bootstrap API key and project info |
| `GET` | `/setup/health` | Check Hub setup status |

Used by `agentweave activate` to auto-configure HTTP transport without manual API key entry.

### Agent Trigger

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/trigger` | Trigger an agent to process messages |
| `GET` | `/sessions/{agent}` | Get active sessions for an agent |

## SSE Events

The Hub exposes Server-Sent Events endpoints for real-time updates:

### Live Events Stream

```
GET /api/v1/events
```

Connect with an `Authorization` header to receive live task, message, and log events.

### Event History

```
GET /api/v1/events/history
```

Query historical events with optional filters.

## MCP Server

The Hub also exposes an MCP server endpoint at:

```
POST /api/v1/mcp
```

This provides the same tools as the local MCP server but via the Hub's HTTP transport.
