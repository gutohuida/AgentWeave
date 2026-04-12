# Watchdog

The AgentWeave watchdog is a background process that monitors the collaboration state and triggers agents when new messages or tasks arrive.

## Overview

The watchdog (`agentweave-watch`) runs as a detached daemon process, continuously:

1. Monitoring for new messages and tasks
2. Triggering agents via their configured runners
3. Managing retry logic for failed triggers
4. Tracking agent session state

## Starting and Stopping

```bash
# Start the watchdog
agentweave start

# Start with custom retry interval (default: 600 seconds = 10 minutes)
agentweave start --retry-after 300

# Stop the watchdog
agentweave stop
```

The watchdog PID is stored in `.agentweave/watchdog.pid` and logs to `.agentweave/logs/watchdog.log`.

## How It Works

### 1. Monitoring Loop

The watchdog runs a continuous loop with a 5-second poll interval:

```python
while running:
    # Check each agent for pending work
    for agent in session_agents:
        if has_pending_work(agent):
            trigger_agent(agent)
    
    sleep(5)
```

### 2. Transport-Specific Monitoring

**LocalTransport:**
- Watches `.agentweave/messages/pending/` directory
- Scans for new JSON message files

**GitTransport:**
- Polls the remote orphan branch
- Fetches new messages via `git fetch`
- Processes files not yet seen locally

**HttpTransport:**
- Polls Hub API for pending messages
- Receives real-time updates via SSE when connected
- Pushes agent output back to Hub

### 3. Agent Triggering

When work is detected, the watchdog triggers the agent based on its runner configuration:

| Runner | Trigger Mechanism |
|--------|-------------------|
| `native`/`claude` | Launches `claude` subprocess with relay prompt |
| `claude_proxy` | Launches with `ANTHROPIC_BASE_URL` override |
| `kimi` | Launches `kimi` subprocess with context |
| `manual` | Logs notification (requires human action) |

### 4. Auto-Ping and Retry Logic

If an agent doesn't respond to a message within the retry window (default 10 minutes), the watchdog re-triggers:

```python
if message_age > retry_after and not agent_responded:
    trigger_agent(agent)  # Re-ping
```

This ensures messages aren't lost if an agent crashes or the CLI isn't running.

### 5. Stale Process Cleanup

When starting, the watchdog:

1. Checks for existing watchdog processes
2. Sends SIGTERM to any stale daemons
3. Removes stale PID files
4. Starts fresh

This prevents multiple watchdogs from conflicting.

## Pilot Mode Handling

When an agent is in **pilot mode**, the watchdog:

- Skips auto-triggering
- Still tracks pending work
- Logs that manual intervention is required

The agent can be triggered manually via the Hub UI or CLI.

## Session Routing

### New Sessions

By default, triggered agents start fresh sessions. The watchdog:

1. Generates a relay prompt with pending work
2. Launches the CLI without `--resume`
3. The agent reads context files fresh

### Resuming Sessions

For claude_proxy agents with saved session IDs:

1. Retrieves session ID from `.agentweave/agents/{agent}-session.json`
2. Launches with `--resume <session_id>`
3. Conversation context is preserved

For jobs with `session_mode: resume`:
- Uses the `last_session_id` from the job record
- Falls back to new session if none exists

## Output Streaming (HTTP Transport)

When using the Hub with HTTP transport:

1. Watchdog captures agent stdout/stderr
2. Parses JSONL stream from Claude CLI
3. Extracts content and thinking blocks
4. Pushes to Hub via `POST /api/v1/agents/{name}/output`
5. Dashboard displays real-time output

## Process Architecture

```
┌─────────────────┐
│   Watchdog      │  (daemon process)
│  (agentweave-   │
│    watch)       │
└────────┬────────┘
         │
    ┌────┴────┬────────────┬──────────────┐
    │         │            │              │
    ▼         ▼            ▼              ▼
┌───────┐ ┌───────┐ ┌──────────┐ ┌─────────────┐
│ Local │ │  Git  │ │   Hub    │ │ Agent       │
│ Files │ │Remote │ │   API    │ │ Processes   │
└───────┘ └───────┘ └──────────┘ └─────────────┘
```

## Configuration

The watchdog reads configuration from:

- `.agentweave/session.json` — agent list and runner configs
- `.agentweave/transport.json` — transport settings
- CLI flags (`--retry-after`) — retry behavior

## Troubleshooting

### Watchdog not starting

Check if `.agentweave/` directory exists:

```bash
agentweave init --project "My Project" --agents claude,kimi
```

### Stale PID file

If the watchdog crashed, remove the PID file manually:

```bash
rm .agentweave/watchdog.pid
agentweave start
```

### Agents not being triggered

1. Check watchdog is running:
   ```bash
   agentweave status
   ```

2. Verify agent runner configuration:
   ```bash
   agentweave transport status
   ```

3. Check watchdog logs:
   ```bash
   cat .agentweave/logs/watchdog.log
   ```

### Multiple watchdogs running

The watchdog automatically kills stale processes on startup. If issues persist:

```bash
# Linux/macOS
pkill -f agentweave-watch

# Windows
taskkill /F /IM agentweave-watch.exe
```

Then restart:

```bash
agentweave start
```

## See Also

- [CLI Commands: Watchdog](../reference/cli-commands.md#watchdog)
- [Transport Layer](transport-layer.md)
- [Messaging System](messaging.md)
