## Context

AgentWeave currently requires 5+ distinct setup steps and 10+ commands before a project is usable. Each agent configuration change (runner, roles, model, yolo, pilot) requires a separate imperative CLI call. There is no single source of truth for what a project's team looks like — that information is scattered across `session.json`, `roles.json`, and `transport.json`.

The system already stores agent config in structured JSON (`session.json` has `agents` dict with keys `role`, `runner`, `env_vars`, `model`, `yolo`, `pilot`). The runtime plumbing exists; what's missing is a human-friendly declarative interface over it and a Hub lifecycle management layer.

## Goals / Non-Goals

**Goals:**
- Reduce first-time setup to 3 memorable commands with no flags to look up
- Replace all agent/transport/roles/jobs configuration commands with a single YAML file
- Hub API key management requires zero manual steps
- `agentweave activate` is idempotent — safe to re-run at any time
- Existing operational commands are completely untouched

**Non-Goals:**
- Shared/remote Hub support (future work)
- Changing the task, message, relay, or checkpoint command interfaces
- Replacing `session register` (remains imperative — session IDs are machine-local runtime state)
- GUI or TUI setup wizard

---

## Decisions

### Decision 1: Single `agentweave.yml` at project root vs. multiple files

**Chosen: Single `agentweave.yml` at project root**

One file describes the entire project team configuration: project metadata, Hub connection, agents, and optional jobs. Committed to git alongside source code.

Alternatives considered:
- `.agentweave/agents.yml` + `.agentweave/jobs.yml` — more granular but harder to discover and more files to manage
- Extending `AI_CONTEXT.md` with a YAML front matter block — pollutes the human-readable context file with machine config

**Rationale**: Mirrors the `docker-compose.yml` pattern — one file per project that defines the full stack. Easier to onboard new team members (clone repo, see exactly what's needed).

---

### Decision 2: Hub API key auto-generation strategy

**Chosen: Hub generates key on first startup; exposes it on a localhost-only `/setup/token` GET endpoint**

On first startup, if no API key exists, Hub generates one (`aw_live_<random32>`), stores it in the database, and makes it available at `GET /setup/token` — only accessible from `127.0.0.1`. The CLI calls this endpoint after `hub start` and writes `transport.json` automatically.

Alternatives considered:
- Keep manual `.env` editing — current approach, too much friction
- Auto-generate key and print it to stdout for user to copy — still requires manual step
- Write key to a file in the Docker volume and mount it — complex, platform-dependent

**Rationale**: Zero-touch key management. Users never see or touch the key unless they need to. The localhost-only constraint means the endpoint is safe without auth — only processes on the same machine can call it.

---

### Decision 3: `agentweave activate` reconciliation scope

**Chosen: Activate reconciles configuration state only, never touches runtime state**

`agentweave activate` reads `agentweave.yml` and reconciles:
- `transport.json` (Hub connection)
- `session.json` agents section (add new agents, update existing config)
- `roles.json` (agent role assignments)
- MCP server registration
- Watchdog process (starts if not running)

It does NOT:
- Delete agents removed from the YAML (tasks/messages may reference them)
- Cancel or modify active tasks
- Wipe message history

Alternatives considered:
- Full destructive reconciliation (delete removed agents) — too dangerous, could lose in-progress work
- Only update what's explicitly changed (diff-based) — complex to implement correctly

**Rationale**: Configuration and runtime state have different lifecycles. The YAML is the desired configuration; `session.json` is living state. Activate is additive for agents — you can add and update, but removal is deliberate (manual `agentweave agent remove` if needed in future).

---

### Decision 4: `agentweave hub start` implementation

**Chosen: CLI downloads `docker-compose.yml` and `.env` to `~/.agentweave/hub/`, runs `docker compose up -d` from there**

Hub files live globally in `~/.agentweave/hub/` — one Hub serves all projects. The CLI manages the lifecycle from any directory.

Alternatives considered:
- Download to current directory — Hub is per-project, but it's really per-machine
- Require user to manually download files — current approach, too many steps

**Rationale**: The Hub is a machine-level service, not a project-level one. Global install matches user mental model: "start the Hub once, use it for all projects."

---

### Decision 5: `env:` section in agentweave.yml for secrets

**Chosen: `env:` lists env var names only; values come from shell or `.env` file**

```yaml
agents:
  minimax:
    env:
      - MINIMAX_API_KEY
```

The YAML names which variables to pass through to the agent process. Actual values come from the shell environment or a gitignored `.env` file in the project root.

**Rationale**: `agentweave.yml` is committed to git. Secrets must never appear there. This follows the Docker Compose convention exactly — maximum familiarity, clear separation.

---

## Risks / Trade-offs

**Risk: `/setup/token` endpoint could be called by local malicious processes**
→ Mitigation: Restrict to `127.0.0.1` in Hub middleware. Document that the endpoint is disabled after first CLI connection (Hub can revoke after first successful `activate`). Low risk for local dev use case.

**Risk: `agentweave activate` is additive — removed agents accumulate in session.json**
→ Mitigation: Activate prints a notice when it detects agents in session.json not in the YAML: "Agent 'kimi' is in session but not in agentweave.yml — run `agentweave agent remove kimi` to clean up." Explicit, not automatic.

**Risk: `docker-compose.yml` format changes between Hub versions**
→ Mitigation: `agentweave hub start` always downloads the latest compose file from the release tag matching the installed CLI version. Pin to version, don't use `master`.

**Risk: Users with existing projects have `session.json` but no `agentweave.yml`**
→ Mitigation: `agentweave init` detects existing session and offers to generate `agentweave.yml` from current `session.json` state. Migration path is non-destructive.

---

## Migration Plan

1. **Existing projects** — `agentweave init` detects `.agentweave/session.json` and generates `agentweave.yml` from current state. No data lost.
2. **`--agents` flag on init** — Deprecated with a warning; still works for one release cycle, then removed.
3. **Old imperative commands** — `transport setup`, `roles add/set/remove`, `agent configure` continue to work but print a deprecation notice pointing to `agentweave.yml`.
4. **Hub `.env` with manually set key** — `agentweave hub start` respects existing `.env`; auto-generation only happens if no key is set.

## Open Questions

- Should `agentweave activate` start the watchdog automatically, or keep that as an explicit `agentweave start`? (Proposal says yes — activate does everything. But some users may want to connect without starting the watchdog.)
- Should the `jobs:` section in `agentweave.yml` sync to Hub jobs on activate, or require a separate `agentweave jobs sync` command?
