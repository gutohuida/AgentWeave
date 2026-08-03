# Alternative Modes

AgentWeave supports a Hub with either injected tools or ordinary commands, plus manual relay for zero-infrastructure experiments.

## Mode Comparison

| Mode | Setup | Best For |
|------|-------|----------|
| **Hub** | Docker + HTTP transport | Teams, multi-machine, web dashboard *(recommended)* |
| **Hub command path** | Hub + `hub_client: cli` | Environments that prohibit tool-protocol servers |
| **Manual relay** | Zero setup | Quick one-off delegation |

## Hub Command Path (No Tool-Protocol Server)

The Hub still owns execution, queues, budgets, and attribution, but tells the runner to use ordinary
`agentweave` commands instead of injecting its tool-protocol server.

```bash
pip install "agentweave-ai[all]"
cd your-project/
agentweave init --project "My App"
agentweave hub start
# Set agents.<name>.hub_client: cli in agentweave.yml
agentweave activate
```

Inbound entries are delivered inline at turn start. The command path retains messaging, task,
question, and budgeted agent-request capabilities without inbox polling.

## Manual Relay (Simplest Possible)

The original AgentWeave mode — zero dependencies, zero background processes.

```bash
pip install agentweave-ai
cd your-project/
agentweave init --project "My App"
```

Then just ask Claude to delegate. It runs `agentweave quick` and `agentweave relay`, and gives you a prompt to paste into Kimi (or any other agent).

```bash
agentweave quick --to kimi "Please refactor the auth module"
agentweave relay --agent kimi
```

Copy the output, switch to your Kimi session, paste it in. When Kimi finishes, copy its response back to Claude.

## When to Use Which

- **Just trying it out?** → Manual relay
- **Tool-protocol server prohibited?** → Hub command path
- **Team, multiple machines, or you want a dashboard?** → Hub
