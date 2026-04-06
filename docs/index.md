# AgentWeave

**A collaboration framework for N AI agents — Claude, Kimi, Gemini, Codex, Minimax, GLM, and more.**

AgentWeave lets multiple AI agents work together on the same project through a shared protocol. The **AgentWeave Hub** is a self-hosted server with a web dashboard — the recommended way to run it.

## Quick Start

Get up and running in 5 minutes:

```bash
# 1. Start the Hub (Docker)
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/docker-compose.yml
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/.env.example
cp .env.example .env
# Edit .env and set AW_BOOTSTRAP_API_KEY
docker compose up -d

# 2. Install the CLI
pip install "agentweave-ai[mcp]"

# 3. Initialize your project
cd /path/to/your-project
agentweave init --project "My App" --agents claude,kimi

# 4. Connect to the Hub
agentweave transport setup --type http \
  --url http://localhost:8000 \
  --api-key aw_live_<your-key> \
  --project-id proj-default

# 5. Start the watchdog
agentweave mcp setup
agentweave start
```

See the [Getting Started](getting-started/quickstart.md) guide for full details.

---

## What is AgentWeave?

AgentWeave solves a simple but important problem: **how do you get multiple AI agents to collaborate on the same codebase?**

It provides:

- **A shared protocol** — tasks, messages, and context files that all agents can read and write
- **Multiple transport modes** — local filesystem, git orphan branch, or HTTP via the Hub
- **An MCP server** — native tool integration so agents can send messages and manage tasks autonomously
- **A web dashboard** — real-time visibility into agent activity, tasks, and messages

## Three Modes of Operation

| Mode | Setup | Best For |
|------|-------|----------|
| **Hub** | Docker + HTTP transport | Teams, multi-machine, web dashboard *(recommended)* |
| **Zero-relay MCP** | `agentweave mcp setup` + watchdog | Autonomous loops, same machine, no server |
| **Manual relay** | Zero setup | Quick one-off delegation |

## Documentation

| Section | Description | Links |
|---------|-------------|-------|
| **Getting Started** | Install the CLI, start the Hub, and connect your first agents | [Installation](getting-started/installation.md) · [Quick Start](getting-started/quickstart.md) |
| **Guides** | Step-by-step guides for common tasks and workflows | [Adding New Agents](guides/adding-new-agents.md) · [Context Files](guides/context-files.md) · [Session Modes](guides/session-modes.md) · [AW-Spec Workflow](guides/aw-spec-workflow.md) · [Dashboard](guides/dashboard.md) · [FAQ](guides/faq.md) |
| **Reference** | CLI commands, MCP tools, API endpoints, and configuration options | [CLI Commands](reference/cli-commands.md) · [MCP Tools](reference/mcp-tools.md) · [Task Lifecycle](reference/task-lifecycle.md) · [Hub API](reference/hub-api.md) |
| **Architecture** | Understand how AgentWeave works under the hood | [Overview](architecture/overview.md) · [Transport Layer](architecture/transport-layer.md) · [Messaging](architecture/messaging.md) · [Locking](architecture/locking.md) |
| **Contributing** | Development setup and release process | [Development](contributing/development.md) · [Release Process](contributing/release-process.md) |

## Dashboard Features

Open **http://localhost:8000** to see:

- **Mission Control** — centralized overview of session status and activity
- **Tasks board** — all tasks with status, priority, assignee, and deliverables
- **Messages feed** — inter-agent messages with inline task linking
- **Human questions** — answer agent questions directly in the UI
- **Agent activity** — live event stream, per-agent output logs, and session management
- **Agent chat** — per-session chat history with session selector
- **Agent cards** — connected agents with multi-role badges, yolo mode, and runner type

See [Using the Dashboard](guides/dashboard.md) for more.
