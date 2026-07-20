---
name: aw-setup-transport
description: Choose and configure how agents exchange messages — local (single machine), git (cross-machine via orphan branch), or http (AgentWeave Hub). Use when changing transport, adding a second machine, or debugging message delivery. For full project setup use aw-setup; for Hub specifics use aw-setup-hub.
---

Configure the message transport for this project.

**Project:** {project_name} — **agents:** {agents_list}

## 1. Pick a transport

| Transport | When | Requires |
|---|---|---|
| `local` (default) | All agents on this one machine | nothing |
| `git` | Agents on different machines, no server wanted | a git remote both machines can push/pull |
| `http` | AgentWeave Hub (dashboard, team use) | a running Hub + API key |

Check the current state first:

```bash
agentweave transport status
```

## 2A. Local (default)

Nothing to configure — if a transport was set up before and you want to go back:

```bash
agentweave transport disable
```

## 2B. Git transport

Messages ride an orphan branch (default `agentweave/collab`) on your existing remote; the working tree is never touched.

```bash
agentweave transport setup --type git                      # remote origin, default branch
agentweave transport setup --type git --remote upstream    # different remote
agentweave transport setup --type git --cluster alice      # multi-workspace branch sharing
```

- `--cluster <name>`: use when several people/machines share the remote. Each workspace gets a name and messages are stamped `<cluster>.<agent>` so they can be addressed individually. Every machine on the shared branch needs its own distinct cluster name.
- Run the setup on **each** machine, then `agentweave transport pull` (or let the watchdog poll) to fetch remote messages.

## 2C. HTTP transport (Hub)

```bash
agentweave transport setup --type http \
  --url http://localhost:8000 \
  --api-key aw_live_<key> \
  --project-id proj-<id>
```

If `hub.url` is set in `agentweave.yml`, `agentweave activate` does this automatically — it fetches the API key from the Hub's setup endpoint and writes the transport config. Prefer that path; use the manual command when the auto-fetch is not possible (e.g. custom auth setup). See `aw-setup-hub` for starting a Hub.

## 3. Verify

```bash
agentweave transport status    # type, remote/url, last sync
agentweave transport pull      # force a fetch now (git)
agentweave doctor              # full readiness check
```

Then send a test message and confirm the other side receives it:

```bash
agentweave msg send --to <other-agent> --subject "ping" --message "transport test"
```

## Notes

- `.agentweave/transport.json` holds the transport config — including the Hub API key for http. It is **gitignored**: each machine configures its own transport. Never commit it.
- Switching transports does not migrate pending messages; drain inboxes (`agentweave inbox`) before switching.
