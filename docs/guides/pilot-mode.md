# Pilot Mode

Pilot Mode gives you explicit control over agent sessions, allowing you to manage long-running agent processes with proper session tracking and registration. It's particularly useful when working with Kimi Code CLI or when you need precise control over session lifecycles.

## What is Pilot Mode?

By default, AgentWeave's watchdog automatically triggers agents when new messages or tasks arrive. In Pilot Mode:

- Agents are registered but **not auto-triggered**
- You manually control when agents start and resume
- Session IDs are tracked and registered with the Hub
- Agent state is visible in the dashboard

## When to Use Pilot Mode

Use Pilot Mode when:

- **Working with Kimi Code CLI** - Register session IDs for proper context management
- **Running agents on different machines** - Track which agent is where
- **Avoiding auto-execution** - You want manual control over agent triggers
- **Managing long-running sessions** - Resume previous conversations intentionally

## Enabling Pilot Mode

### For Any Agent

```bash
agentweave agent configure <agent> --pilot
```

Example:

```bash
agentweave agent configure kimi --pilot
```

### During Initial Configuration

```bash
agentweave agent configure kimi --runner kimi --pilot
```

### Disable Pilot Mode

```bash
agentweave agent configure <agent> --no-pilot
```

## Registering Sessions

Once an agent is in Pilot Mode, register its session ID so AgentWeave can track it:

### 1. Start Your Agent

Start your agent normally and get its session ID:

**For Kimi:**
```bash
kimi --agent-file .agentweave/agent-kimi.yaml
# Note the session ID from output: "Session: abc123..."
```

**For Claude:**
```bash
claude --resume <previous-session> --append-system-prompt-file .agentweave/context/claude.md
# Or start fresh and note the new session ID
```

### 2. Register the Session

```bash
agentweave session register --agent kimi --session <session-id>
```

This:
- Registers the session with the Hub (if HTTP transport)
- Updates local agent session file
- Prints the ready-to-use launch command

## Kimi Pilot Workflow

AgentWeave can auto-generate Kimi configuration files for seamless pilot integration:

### 1. Configure with Pilot Flag

```bash
agentweave agent configure kimi --runner kim --pilot
```

This generates:
- `.agentweave/context/kimi.md` - Context file with role guides
- `.agentweave/agent-kimi.yaml` - Kimi agent configuration

### 2. Start Kimi

```bash
kimi --agent-file .agentweave/agent-kimi.yaml
```

### 3. Register the Session

After Kimi starts and shows its session ID:

```bash
agentweave session register --agent kimi --session <session-id>
```

### 4. Future Launches

Now you can resume with:

```bash
kimi --agent-file .agentweave/agent-kimi.yaml --session <session-id>
```

## Claude Proxy Pilot Workflow

For claude_proxy agents (Minimax, GLM, etc.), Pilot Mode works similarly:

### 1. Configure Agent

```bash
agentweave agent configure minimax --pilot
```

### 2. Start and Register

```bash
# Start the agent
agentweave run --agent minimax
# Note the session ID

# Register it
agentweave session register --agent minimax --session <session-id>
```

### 3. Set Model (Optional)

```bash
agentweave agent set-model minimax MiniMax-Text-01
```

## Viewing Pilot Agents in Dashboard

When using the Hub with HTTP transport:

1. Open the dashboard at `http://localhost:8000`
2. Navigate to **Mission Control**
3. Pilot agents show:
   - **Pilot badge** - Indicates pilot mode is active
   - **Registered session ID** - The current session
   - **Manual trigger button** - Trigger without auto-ping

## Session Management

### Checking Registered Sessions

```bash
agentweave status
```

Shows pilot status for each agent.

### Updating a Session

If you start a new session, re-register:

```bash
agentweave session register --agent kimi --session <new-session-id>
```

The old session is replaced - Hub tracks only the current session per agent.

### Session Persistence

- **Local**: Session stored in `.agentweave/agents/<agent>-session.json`
- **Hub**: Session stored in `agents.registered_session_id` column
- Both are updated when you run `session register`

## Pilot Mode vs Auto-Trigger

| Feature | Normal Mode | Pilot Mode |
|---------|-------------|------------|
| Watchdog auto-trigger | ✅ Yes | ❌ No |
| Session registration | Optional | Required |
| Dashboard visibility | Yes | Yes (+ pilot badge) |
| Manual control | Limited | Full |
| Best for | Hands-off automation | Explicit session management |

## Combining with Yolo Mode

Pilot agents can still use Yolo mode for confirmation suppression:

```bash
# Enable yolo for a pilot agent
agentweave yolo --agent kimi --enable
```

This means:
- You manually trigger the agent (Pilot)
- When triggered, it acts without confirmations (Yolo)

## MCP Tools

Agents can register their own sessions via MCP:

```python
# Register current session
register_session(
    from_agent="kimi",
    session_id="abc123..."
)

# Get agent config (includes pilot status)
config = get_agent_config("kimi")
# Returns: {"runner": "kimi", "pilot": true, ...}
```

## Troubleshooting

### "No session found" when registering

Ensure you've initialized AgentWeave:

```bash
agentweave init --project "My Project" --agents claude,kimi
```

### Session not showing in Hub

1. Verify HTTP transport is configured:
   ```bash
   agentweave transport status
   ```

2. Check Hub connectivity

3. Re-register the session

### Kimi YAML not generated

Make sure to use `--pilot` when configuring:

```bash
agentweave agent configure kimi --runner kim --pilot
```

If still missing, manually generate:

```bash
agentweave sync-context --agent kimi
```

## See Also

- [CLI Commands Reference](../reference/cli-commands.md#session)
- [MCP Tools Reference](../reference/mcp-tools.md)
- [Claude Proxy Agents](claude-proxy-agents.md)
