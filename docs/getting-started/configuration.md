# Configuration

This guide covers the main configuration options for AgentWeave.

---

## Primary Configuration: `agentweave.yml`

`agentweave.yml` is the **single source of truth** for your AgentWeave project. It lives at your project root and should be committed to version control.

```yaml
project:
  name: "My Awesome App"
  mode: hierarchical

hub:
  url: http://localhost:8000

agents:
  claude:
    runner: claude
    roles:
      - tech_lead
    yolo: false

  kimi:
    runner: kimi
    pilot: true

  minimax:
    runner: claude_proxy
    model: MiniMax-Text-01
    env:
      - MINIMAX_API_KEY
    yolo: true

jobs:
  daily-standup:
    schedule: "0 9 * * 1-5"
    agent: claude
    prompt: "Generate a daily standup summary"
    enabled: true
```

After editing, apply changes with:

```bash
agentweave activate
```

This idempotent command:
- Configures transport (auto-fetches API key from Hub if needed)
- Syncs agents to `session.json`
- Sets up MCP
- Starts the watchdog
- Syncs jobs
- Regenerates context files

See the [agentweave.yml Reference](../reference/agentweave-yml.md) for the complete schema.

---

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

---

## Transport Configuration

When using `agentweave activate`, HTTP transport is configured automatically from the `hub` section of `agentweave.yml`. You only need manual transport setup for advanced cases or non-HTTP modes.

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

---

## Agent Configuration

### Declarative (Recommended)

Edit `agentweave.yml` under the `agents:` section, then run `agentweave activate`.

### Imperative (Legacy)

These commands still work for one-off changes:

#### Yolo Mode

```bash
agentweave yolo --agent claude --enable
agentweave yolo --agent claude --disable
```

#### Claude-Proxy Agents

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

---

## Project Files

After `agentweave init`, you'll have:

- `agentweave.yml` — project configuration (commit this)
- `.agentweave/session.json` — session config (gitignored)
- `.agentweave/transport.json` — transport config (gitignored)
- `.agentweave/roles.json` — agent role assignments
- `.agentweave/roles/*.md` — per-role behavioral guides
- `AI_CONTEXT.md` — project stack and architecture
- `AGENTS.md` — agent-specific coding guidelines

**Safe to commit:** `agentweave.yml`, `AI_CONTEXT.md`, `AGENTS.md`, `.agentweave/roles.json`, `.agentweave/roles/*.md`, `.agentweave/README.md`, `.agentweave/protocol.md`

**Never commit:** `session.json`, `transport.json`, tasks, messages, logs

---

## See Also

- [Quick Start](quickstart.md) — get running in 5 minutes
- [agentweave.yml Reference](../reference/agentweave-yml.md) — complete YAML schema
- [CLI Commands Reference](../reference/cli-commands.md) — all available commands
- [Environment Variables Reference](../reference/env-variables.md) — complete variable listing
- [Migration Guide](migration.md) — migrating from old imperative setup
