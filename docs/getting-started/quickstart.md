# Quick Start

Get started with AgentWeave in **3 commands**. No manual configuration needed.

## Prerequisites

- Python 3.8+ installed
- Docker and Docker Compose installed
- A project directory you want agents to collaborate on

---

## Step 1 — Start the Hub

The Hub manages agent communication and provides a web dashboard.

```bash
agentweave hub start
```

This downloads the Hub configuration, starts the Docker container, and fetches the API key automatically. The Hub will be available at **http://localhost:8000**.

---

## Step 2 — Initialize Your Project

Navigate to your project and run:

```bash
cd /path/to/your-project
agentweave init --project "My App"
```

This creates:

- `agentweave.yml` — your project configuration (edit to add/remove agents)
- `.agentweave/` — shared context, roles, and protocol files
- `CLAUDE.md` / `AGENTS.md` — agent context files at project root

---

## Step 3 — Activate

Apply your configuration and start collaborating:

```bash
agentweave activate
```

This single command:
- Connects the CLI to the Hub
- Registers all agents from `agentweave.yml`
- Sets up MCP for agent communication
- Starts the background watchdog

---

## You're Ready!

Open **http://localhost:8000** to see the dashboard. Your agents can now:

- Send messages to each other via the Hub
- Create and manage tasks
- Ask you questions when they need clarification

Start your first agent (Claude, Kimi, etc.) in your project directory — it will auto-read its context file.

---

## Daily Workflow

### Check Status

```bash
agentweave status
```

### Add a New Agent

Edit `agentweave.yml`:

```yaml
agents:
  claude:
    runner: claude
  kimi:
    runner: kimi
  gemini:          # Add new agent
    runner: native
```

Then run `agentweave activate` to apply changes.

### Stop Everything

```bash
agentweave hub stop      # Stop the Hub
agentweave stop          # Stop the watchdog
```

---

## What's Next?

- [Configuration Guide](configuration.md) — `agentweave.yml` reference and options
- [Context Files](../guides/context-files.md) — how `ai_context.md` and agent files work
- [Session Modes](../guides/session-modes.md) — hierarchical vs peer vs review
- [CLI Commands Reference](../reference/cli-commands.md) — full command listing
- [MCP Tools Reference](../reference/mcp-tools.md) — tools available to agents
- [Using the Dashboard](../guides/dashboard.md) — what you'll see at localhost:8000
- [FAQ](../guides/faq.md) — common questions and answers

---

## Troubleshooting

### "Docker is not available"

Make sure Docker Desktop (Mac/Windows) or Docker Engine (Linux) is running:

```bash
docker --version
docker compose version
```

### "No agentweave.yml found"

Run `agentweave init` in your project directory first.

### "Hub failed to start"

Check the Hub logs:

```bash
docker compose -f ~/.agentweave/hub/docker-compose.yml logs
```

### Need to reset everything?

```bash
agentweave hub stop
agentweave stop
rm -rf .agentweave/ agentweave.yml CLAUDE.md AGENTS.md
```

Then start over from Step 1.
