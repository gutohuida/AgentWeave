# Migration Guide

## Upgrading from Manual Setup

If you have an existing AgentWeave project using the old imperative commands, this guide shows you how to migrate to the new declarative `agentweave.yml` workflow.

---

## What's Changed

| Before | After |
|--------|-------|
| `agentweave init --agents claude,kimi` | `agentweave init` (no `--agents` needed) |
| `agentweave transport setup --type http ...` | Handled by `agentweave activate` |
| `agentweave mcp setup` | Handled by `agentweave activate` |
| `agentweave start` | Handled by `agentweave activate` |
| `agentweave agent configure <agent> ...` | Edit `agentweave.yml` + `agentweave activate` |
| `agentweave agent set-model <agent> ...` | Edit `agentweave.yml` + `agentweave activate` |
| `agentweave yolo --agent <agent> --enable` | Edit `agentweave.yml` + `agentweave activate` |
| `agentweave jobs create ...` | Add to `agentweave.yml` + `agentweave activate` |

---

## Migration Steps

### 1. Ensure You're Up to Date

```bash
pip install --upgrade "agentweave-ai[mcp]"
```

### 2. Generate agentweave.yml from Existing Session

If you have an existing `.agentweave/session.json`:

```bash
cd /path/to/your-project
agentweave init
```

This detects your existing session and generates `agentweave.yml` with your current agents and configuration.

### 3. Review the Generated File

```bash
cat agentweave.yml
```

You'll see something like:

```yaml
# AgentWeave Configuration
project:
  name: "My Existing Project"
  mode: hierarchical

hub:
  url: http://localhost:8000

agents:
  claude:
    runner: claude
    yolo: false
  kimi:
    runner: kimi
    pilot: false
```

### 4. Add Any Missing Configuration

If you had custom configurations (env vars, models, etc.), add them to `agentweave.yml`:

```yaml
agents:
  claude:
    runner: claude
    roles:
      - tech_lead
  
  minimax:
    runner: claude_proxy
    model: MiniMax-M2.7
    env:
      - MINIMAX_API_KEY
    yolo: true
```

### 5. Run Activate

```bash
agentweave activate
```

This will:
- Connect to the Hub (auto-fetching API key if needed)
- Sync agents from `agentweave.yml`
- Set up MCP
- Start the watchdog

### 6. Verify Everything Works

```bash
agentweave status
```

You should see all your agents listed with their configurations.

---

## Old Commands That Still Work

These commands continue to work but may show deprecation warnings:

| Old Command | New Way |
|-------------|---------|
| `agentweave init --agents a,b,c` | `agentweave init` then edit `agentweave.yml` |
| `agentweave transport setup ...` | `agentweave activate` handles this |
| `agentweave mcp setup` | `agentweave activate` handles this |
| `agentweave start` | `agentweave activate` handles this |

---

## Breaking Changes

### `--agents` Flag Deprecated

The `--agents` flag on `init` still works but shows a deprecation warning:

```bash
agentweave init --agents claude,kimi  # Works, but warns
```

**Recommended:** Use `agentweave init` without flags, then edit `agentweave.yml`.

---

## Troubleshooting

### "No agentweave.yml found"

Run `agentweave init` to generate it from your existing session.

### "Configuration error"

Validate your YAML syntax:

```bash
python -c "import yaml; yaml.safe_load(open('agentweave.yml'))"
```

Common issues:
- `env` must be a list (`- VAR_NAME`) not a dict
- `mode` must be `hierarchical`, `peer`, or `review`
- `runner` must be `claude`, `kimi`, `native`, `claude_proxy`, or `manual`

### Need to Roll Back?

Your old session is preserved in `.agentweave/session.json`. The migration is non-destructive.

---

## Benefits of the New Workflow

1. **Single source of truth** — `agentweave.yml` defines your entire team
2. **Version controlled** — Commit agent configuration with your code
3. **Idempotent** — `activate` is safe to run any number of times
4. **Self-documenting** — YAML shows exactly what's configured
5. **Easier onboarding** — New team members just run `activate`

---

## Questions?

- [Full agentweave.yml Reference](../reference/agentweave-yml.md)
- [Quick Start Guide](quickstart.md)
- [CLI Commands Reference](../reference/cli-commands.md)
