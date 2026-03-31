# Quick Start

This guide walks you through the recommended setup: **AgentWeave Hub + CLI + MCP**.

## Prerequisites

- Python 3.8+ installed
- Docker and Docker Compose installed
- A project directory you want agents to collaborate on

---

## Step 1 — Start the Hub

```bash
# Download config files
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/docker-compose.yml
curl -O https://raw.githubusercontent.com/gutohuida/AgentWeave/master/hub/.env.example

# Create your environment file
cp .env.example .env
```

Generate a secure API key:

```bash
python -c "import secrets; print('aw_live_' + secrets.token_hex(16))"
```

Paste the result into `.env` as `AW_BOOTSTRAP_API_KEY`, then start the Hub:

```bash
docker compose up -d
```

Open **http://localhost:8000** in your browser to confirm it's running.

---

## Step 2 — Install the CLI

```bash
pip install "agentweave-ai[mcp]"
```

---

## Step 3 — Initialize Your Project

Navigate to your project and run:

```bash
cd /path/to/your-project
agentweave init --project "My App" --agents claude,kimi
```

This creates:

- `AI_CONTEXT.md` — fill this in once with your stack, architecture, and standards
- `.agentweave/` — shared context, roles, and protocol files

---

## Step 4 — Connect the CLI to the Hub

```bash
agentweave transport setup --type http \
  --url http://localhost:8000 \
  --api-key aw_live_<your-key> \
  --project-id proj-default
```

---

## Step 5 — Register MCP and Start the Watchdog

```bash
# Register MCP with all session agents
agentweave mcp setup

# Start the background watchdog
agentweave start
```

Stop it later with:

```bash
agentweave stop
```

Restart your Claude / Kimi sessions so they pick up the new MCP server. That's it — agents can now communicate through the Hub and you can monitor everything in the dashboard.

---

## What's Next?

- [Configuration Guide](configuration.md) — transports, agents, and environment variables
- [Context Files](../guides/context-files.md) — how AI_CONTEXT.md and agent files work
- [Session Modes](../guides/session-modes.md) — hierarchical vs peer vs review
- [CLI Commands Reference](../reference/cli-commands.md) — full command listing
- [MCP Tools Reference](../reference/mcp-tools.md) — tools available to agents
- [Using the Dashboard](../guides/dashboard.md) — what you'll see at localhost:8000
- [FAQ](../guides/faq.md) — common questions and answers
