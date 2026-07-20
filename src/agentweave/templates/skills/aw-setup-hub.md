---
name: aw-setup-hub
description: Set up the AgentWeave Hub for this project — start a local Hub (Docker or native), connect to a remote Hub, or check/stop/destroy an existing one. Use whenever Hub connectivity or the web dashboard is being configured. For full project setup use aw-setup.
---

Set up Hub connectivity for this project.

**Project:** {project_name} — **agents:** {agents_list}

## 1. Which Hub scenario?

Ask the user (or infer):

- **A. Local Hub, Docker** (recommended) — needs Docker + docker compose.
- **B. Local Hub, native** — no Docker; runs uvicorn directly (needs `pip install agentweave-hub`).
- **C. Remote Hub** — already running on another machine; just connect.
- **D. No Hub** — stop here; suggest `aw-setup-transport` for local/git instead.

## 2A/2B. Start a local Hub

```bash
agentweave hub start                # Docker, port 8000
agentweave hub start --port 9000    # different port
agentweave hub start --native       # scenario B: uvicorn, no Docker
```

Notes:
- Config and data live in `~/.agentweave/hub/` (compose file, `.env`, database) — not in the project.
- On first start an API key `aw_live_<hex32>` is generated, printed, and saved to `~/.agentweave/hub/.env`. Record it; agents authenticate with it.
- Useful env vars (in `~/.agentweave/hub/.env`): `AW_PORT`, `AW_BOOTSTRAP_API_KEY`, `AW_BOOTSTRAP_PROJECT_ID`, `DATABASE_URL` (default SQLite; set a PostgreSQL DSN for production), `AW_CORS_ORIGINS`.
- `--local` builds from `./hub/` — Hub development only, not for normal projects.

## 2C. Connect to a remote Hub

```bash
agentweave transport setup --type http \
  --url http://<host>:8000 \
  --api-key aw_live_<key> \
  --project-id proj-<id>
```

Get the key and project ID from whoever runs the Hub (or `~/.agentweave/hub/.env` on that machine).

## 3. Point the project at the Hub

In `agentweave.yml`:

```yaml
hub:
  url: http://localhost:8000   # or the remote URL
```

Then:

```bash
agentweave activate
```

`activate` auto-fetches the API key from the Hub's setup endpoint and writes `.agentweave/transport.json` (http transport) — for a reachable Hub this makes step 2C unnecessary.

## 4. Verify

```bash
agentweave hub status          # is the Hub reachable?
agentweave transport status    # http transport active? authenticated?
agentweave doctor              # end-to-end readiness
```

Dashboard: open the Hub URL in a browser (agent list, task board, message feed, human Q&A).

## 5. Managing the Hub later

```bash
agentweave hub stop                # stop, keep data
agentweave hub destroy             # delete the database (asks to confirm)
agentweave hub destroy --all       # also delete ~/.agentweave/hub/.env (API key)
```

Warn before `destroy`: it permanently wipes tasks, messages, and agent registrations.
