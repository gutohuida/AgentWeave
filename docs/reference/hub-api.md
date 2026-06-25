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
| `POST` | `/agents/{name}/heartbeat` | Post agent heartbeat |
| `POST` | `/agents/{name}/output` | Post agent output log |
| `GET` | `/agents/{name}/output` | Get agent output log |
| `POST` | `/agents/{name}/context-usage` | Record context usage for an agent |
| `POST` | `/agents/{name}/compact` | Record a compaction event for an agent |
| `POST` | `/agents/{name}/new-session` | Record a new agent session event |
| `GET` | `/agents/{name}/timeline` | Get agent timeline events |
| `PUT` | `/agents/roles/config` | Update roles configuration |
| `GET` | `/agents/roles/config` | Get roles configuration |
| `POST` | `/agents/register` | Self-register or re-register an agent |
| `PATCH` | `/agents/{name}` | Update self-registered agent metadata/config |
| `GET` | `/agents/context?role=...` | Fetch a role guide |
| `POST` | `/agents/{name}/register-session` | Register a pilot-mode session ID |
| `POST` | `/agents/{name}/pilot` | Enable or disable pilot mode |

### Agent Chat and Trigger

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/agent/trigger` | Trigger an agent to process a message |
| `GET` | `/agent/sessions/{agent}` | Get known sessions for an agent |
| `GET` | `/agent/{agent}/chat` | Get agent chat history |
| `GET` | `/agent/{agent}/chat/{session_id}` | Get a specific chat session |

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

### Events

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/events/ticket` | Get a short-lived SSE auth ticket |
| `GET` | `/events` | Live SSE stream (use ticket from above) |
| `GET` | `/events/history` | Query historical events |

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
| `GET` | `/jobs/{id}/history` | Get job run history |
| `POST` | `/jobs/{id}/run` | Manually trigger a job |

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
| `GET` | `/setup/token` | Get the bootstrap API key from a local or Docker-internal client |

The Hub health check is available outside the API prefix at `GET /health`.

Used by `agentweave activate` to auto-configure HTTP transport without manual API key entry.

### Project Instructions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/project/instructions` | Get project-wide instructions |
| `PUT` | `/project/instructions` | Update project-wide instructions |

## SSE Events

The Hub exposes Server-Sent Events endpoints for real-time updates:

### SSE Authentication

SSE authentication uses short-lived signed tickets instead of passing API keys in the query string:

```
GET /api/v1/events/ticket   → returns { "ticket": "<short-lived-token>" }
GET /api/v1/events?ticket=<token>
```

**Flow:**
1. Call `GET /api/v1/events/ticket` with `Authorization: Bearer <api-key>` to obtain a ticket.
2. Pass the ticket as a query parameter when opening the SSE stream: `GET /api/v1/events?ticket=<token>`.

Non-SSE endpoints do **not** accept `?token=` query parameters — all REST calls must use the `Authorization` header.

### Live Events Stream

```
GET /api/v1/events
```

Connect using the ticket flow above to receive live task, message, and log events.

### Event History

```
GET /api/v1/events/history
```

Query historical events with optional filters.

## Request Limits

The Hub enforces the following limits on all incoming requests:

| Limit | Value | Notes |
|-------|-------|-------|
| Request body size | 1 MB | HTTP 413 is returned for larger bodies |
| Agent name / ID length | 128 chars | Enforced on create schemas |
| Subject / title length | 256 chars | Enforced on message and task schemas |
| Content length | 10,000 chars | Applies to message content and task descriptions |
| `/agent/{agent}/chat` `limit` | 1–500 | Query parameter clamped to this range |

## MCP Server

The Hub MCP server lives in `hub/hub/mcp_server.py` and is normally run as a stdio process with `HUB_URL`, `HUB_API_KEY`, and `HUB_PROJECT_ID` in the environment:

```bash
python -m hub.mcp_server
```

It can be mounted in FastAPI by an embedding application, but the default Hub app does not mount a `/api/v1/mcp` REST endpoint.
