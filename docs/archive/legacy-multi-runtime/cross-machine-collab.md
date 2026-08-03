# Cross-Machine Collaboration

AgentWeave supports two ways to collaborate across multiple machines: **Git transport** and **Hub transport**.

## Via Git (No Server Required)

Git transport is perfect when you want cross-machine sync without running a server.

```bash
agentweave transport setup --type git --cluster yourname
```

This creates an orphan branch (`agentweave/collab`) on your git remote. Messages and tasks sync through git plumbing commands — your working tree and HEAD are never touched.

**Requirements:** Both developers need access to the same git remote (e.g. `origin`).

### How It Works

1. Agent A sends a message
2. AgentWeave commits it to the orphan branch
3. Agent B's watchdog polls and pulls from the remote
4. Agent B receives the message

### Limitations

- No web dashboard
- No human question-answering UI
- Relies on git push/pull timing

## Via Hub (Recommended for Teams)

Deploy the Hub once, connect all agents via HTTP transport. The dashboard shows all messages, tasks, and human questions in real time.

```bash
# Machine A
agentweave transport setup --type http \
  --url http://hub-ip:8000 \
  --api-key aw_live_<key> \
  --project-id proj-default

# Machine B (same command)
agentweave transport setup --type http \
  --url http://hub-ip:8000 \
  --api-key aw_live_<key> \
  --project-id proj-default
```

### Advantages

- Real-time sync via REST + SSE
- Web dashboard for visibility
- Human question-answering UI
- Better suited for >2 agents

## Choosing Between Them

| Factor | Git Transport | Hub Transport |
|--------|---------------|---------------|
| Server required | No | Yes (Docker) |
| Dashboard | No | Yes |
| Real-time | Near-real-time | Real-time |
| Setup complexity | Low | Medium |
| Best for | 2 devs, simple setup | Teams, visibility, scale |
