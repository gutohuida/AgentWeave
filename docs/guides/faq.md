# Frequently Asked Questions

## Do I need the Hub?

No. Manual relay and local MCP modes work with zero infrastructure. The Hub adds a web dashboard, multi-machine support, and human question-answering.

## Should I put the UI in a separate folder/repo?

No. The UI (`hub/ui/`) is built into the Docker image and served by the Hub at the same port. No second server or CORS config is needed in production.

## Do I need to run CLI commands during my session?

No. After `agentweave init`, just talk to Claude. It runs all `agentweave` commands via Bash automatically.

## Do the watchdog processes need to stay running?

Yes (in local MCP mode or Hub mode). Run `agentweave start` once. If they stop, messages still queue — agents just won't be auto-triggered.

## Should I commit `.agentweave/`?

Partially. Runtime state (tasks, messages, `session.json`, `transport.json`, logs, watchdog files, and `.env`) is gitignored. `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.agentweave/ai_context.md`, `.agentweave/context/*.md`, `.agentweave/roles.json`, `.agentweave/roles/*.md`, `.agentweave/protocol.md`, and `.agentweave/shared/context.md` are safe to commit.

See [Configuration](../getting-started/configuration.md) for the full commit guidance, and [Context Files](context-files.md) for details on the context file system.

## Do both developers need the same git remote for git transport?

Yes. Git transport requires a shared remote (e.g. `origin`).

## How do I use MiniMax or GLM — they don't have a CLI?

Use `agentweave agent configure minimax` (or `glm`) to set them up as `claude_proxy` agents. AgentWeave runs them through the Claude CLI with overridden env vars (`ANTHROPIC_BASE_URL` + `ANTHROPIC_API_KEY`). Export your provider key, then run `agentweave run --agent minimax`.

See [Claude-Proxy Agents](claude-proxy-agents.md) for full details.

## Can I use any OpenAI-compatible provider as an agent?

Yes. Use:

```bash
agentweave agent configure <name> \
  --runner claude_proxy \
  --base-url <url> \
  --api-key-var <VAR>
```

The Claude CLI will proxy requests to that endpoint using your existing API key env var.

## What happens if two agents edit the same task?

AgentWeave uses file-based locking with automatic timeout. Only one agent can modify a task at a time. See [Locking](../architecture/locking.md) for details.

## What is `agentweave.yml`?

`agentweave.yml` is the declarative configuration file for your AgentWeave project. It defines:

- Project name and collaboration mode
- Hub connection settings
- Agent configurations (runner, roles, yolo, pilot, env vars)
- Scheduled jobs

After editing `agentweave.yml`, run `agentweave activate` to apply changes. This file should be committed to version control.

See [agentweave.yml Reference](../reference/agentweave-yml.md) and [Migration Guide](../getting-started/migration.md) for details.

## Why does opencode return `ProviderModelNotFoundError` even though my yml and auth.json are correct?

The yml and `auth.json` are almost always right — the opencode binary that
actually got invoked doesn't list that model. Three common causes (typo,
old binary, wrong binary on `PATH`) and how to fix each are covered in
the [catalog-mismatch decision tree](opencode-models.md#7-catalog-mismatch-troubleshooting)
in the opencode models guide. The quick WSL fix is the
[`cli:` override](opencode-agents.md#pinning-the-opencode-binary-wsl-multi-install-hosts).

## Can I run the Hub without Docker?

The Hub is designed to run via Docker Compose for ease of deployment. You can also run it from source by installing the Hub package and starting the FastAPI server manually, but Docker is the supported path.
