# Architecture Overview

AgentWeave is a multi-agent AI collaboration framework built around a shared protocol and pluggable transport layer.

## Core Concepts

### Session

A **session** represents a collaboration context for a project. It is stored in `.agentweave/session.json` and includes:

- Project name
- Principal agent (in hierarchical mode)
- Collaboration mode: `hierarchical`, `peer`, or `review`
- List of participating agents

### Task

Tasks are the unit of work. They have a structured lifecycle, requirements, acceptance criteria, and deliverables. Tasks are stored in `.agentweave/tasks/{task_id}/`.

### Message

Messages enable agent-to-agent communication. They include sender, recipient, subject, content, type, and optional task linkage. Messages are stored in `.agentweave/messages/{message_id}/`.

### Transport

The transport layer abstracts how tasks and messages move between agents. Three transports are supported:

- **LocalTransport** — filesystem-based, single machine
- **GitTransport** — orphan branch sync, cross-machine without a server
- **HttpTransport** — REST API via the Hub, multi-machine with real-time dashboard

### MCP Server

The Model Context Protocol (MCP) server exposes AgentWeave operations as native tools that AI agents can call directly. This enables zero-relay autonomous collaboration.

### Watchdog

The watchdog is a background process that monitors the shared directory (or polls the Hub) and triggers agents when new messages or tasks arrive.

## Repository Layout

```
AgentWeave/
├── src/agentweave/     CLI package (Python 3.8+, zero runtime deps)
├── hub/                AgentWeave Hub server (FastAPI + React + Docker)
├── docs/               Documentation
├── tests/              CLI unit tests
└── Makefile            Convenience targets
```

## Design Principles

1. **Zero runtime dependencies** for the CLI core
2. **Pluggable transports** — swap local ↔ git ↔ HTTP without changing business logic
3. **File-based locking** — prevents race conditions during concurrent writes
4. **Schema validation** — all state files are validated before saving
5. **Never touch working tree** — GitTransport uses plumbing commands only
