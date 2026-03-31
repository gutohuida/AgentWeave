# Configuration

This guide covers the main configuration options for AgentWeave.

## Hub Environment Variables

Configure the Hub via `.env` in the same directory as `docker-compose.yml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `AW_BOOTSTRAP_API_KEY` | *(required)* | API key created on first start (`aw_live_…`) |
| `AW_BOOTSTRAP_PROJECT_ID` | `proj-default` | Default project ID |
| `AW_BOOTSTRAP_PROJECT_NAME` | `Default Project` | Display name for the default project |
| `AW_PORT` | `8000` | Port the Hub listens on |
| `AW_CORS_ORIGINS` | *(empty)* | Comma-separated allowed origins for CORS |
| `DATABASE_URL` | `sqlite+aiosqlite:///data/agentweave.db` | SQLite path inside the container |

Data persists in a Docker volume (`hub-data`) — no manual backup needed for local use.

## Transport Configuration

### HTTP Transport (Hub)

```bash
agentweave transport setup --type http \
  --url http://localhost:8000 \
  --api-key aw_live_<your-key> \
  --project-id proj-default
```

Check status:

```bash
agentweave transport status
agentweave transport pull
```

Disable:

```bash
agentweave transport disable
```

### Git Transport (Cross-Machine, No Server)

```bash
agentweave transport setup --type git --cluster yourname
```

This creates an orphan branch (`agentweave/collab`) on your git remote. Messages sync through git plumbing — working tree and HEAD are never touched.

## Agent Configuration

### Yolo Mode

Allow an agent to act without confirmations:

```bash
agentweave yolo --agent claude --enable
agentweave yolo --agent claude --disable
```

### Claude-Proxy Agents

For agents like MiniMax or GLM that don't have a native CLI:

```bash
agentweave agent configure minimax
agentweave agent configure glm
```

Or for a custom OpenAI-compatible provider:

```bash
agentweave agent configure mymodel \
  --runner claude_proxy \
  --base-url https://api.example.com/v1 \
  --api-key-var MY_MODEL_API_KEY
```

Register a Claude session ID manually:

```bash
agentweave agent set-session minimax <session-id>
```

## Project Files

After `agentweave init`, you'll have:

- `.agentweave/session.json` — session config (gitignored)
- `.agentweave/transport.json` — transport config (gitignored)
- `.agentweave/roles.json` — agent role assignments
- `.agentweave/roles/*.md` — per-role behavioral guides
- `AI_CONTEXT.md` — project stack and architecture
- `AGENTS.md` — agent-specific coding guidelines

**Safe to commit:** `AI_CONTEXT.md`, `AGENTS.md`, `.agentweave/roles.json`, `.agentweave/roles/*.md`, `.agentweave/README.md`, `.agentweave/protocol.md`

**Never commit:** `session.json`, `transport.json`, tasks, messages, logs

## See Also

- [Quick Start](quickstart.md) — get running in 5 minutes
- [CLI Commands Reference](../reference/cli-commands.md) — all available commands
- [Environment Variables Reference](../reference/env-variables.md) — complete variable listing
