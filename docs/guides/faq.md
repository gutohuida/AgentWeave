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

Partially. Runtime state (tasks, messages, `session.json`, `transport.json`) is gitignored. `AGENTS.md`, `AI_CONTEXT.md`, `.agentweave/roles.json`, and `.agentweave/roles/*.md` are safe to commit.

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

## Can I run the Hub without Docker?

The Hub is designed to run via Docker Compose for ease of deployment. You can also run it from source by installing the Hub package and starting the FastAPI server manually, but Docker is the supported path.
