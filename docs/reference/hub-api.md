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

### Status

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | Session-wide summary and task counts |

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
