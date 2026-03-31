# Alternative Modes

AgentWeave supports three operating modes. The Hub is recommended for most users, but the other modes work with zero infrastructure.

## Mode Comparison

| Mode | Setup | Best For |
|------|-------|----------|
| **Hub** | Docker + HTTP transport | Teams, multi-machine, web dashboard *(recommended)* |
| **Zero-relay MCP** | `agentweave mcp setup` + watchdog | Autonomous loops, same machine, no server |
| **Manual relay** | Zero setup | Quick one-off delegation |

## Zero-Relay MCP (No Hub)

In this mode, agents communicate directly through the local MCP server and a background watchdog keeps everything in sync.

```bash
pip install "agentweave-ai[mcp]"
cd your-project/
agentweave init --project "My App" --agents claude,kimi
agentweave mcp setup   # configure MCP in agent settings
agentweave start       # start background watchdog
```

Agents will auto-poll for new messages and tasks. No web dashboard, but fully autonomous.

## Manual Relay (Simplest Possible)

The original AgentWeave mode — zero dependencies, zero background processes.

```bash
pip install agentweave-ai
cd your-project/
agentweave init --project "My App" --agents claude,kimi
```

Then just ask Claude to delegate. It runs `agentweave quick` and `agentweave relay`, and gives you a prompt to paste into Kimi (or any other agent).

```bash
agentweave quick --to kimi "Please refactor the auth module"
agentweave relay --agent kimi
```

Copy the output, switch to your Kimi session, paste it in. When Kimi finishes, copy its response back to Claude.

## When to Use Which

- **Just trying it out?** → Manual relay
- **Solo developer, same machine?** → Zero-relay MCP
- **Team, multiple machines, or you want a dashboard?** → Hub
