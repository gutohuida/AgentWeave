# Task: Hub & MCP Server Support for Minimax / GLM (claude_proxy agents)

**Assignee:** Kimi
**Date:** 2026-03-30
**Repo:** https://github.com/gutohuida/AgentWeave

---

## 1. Background & Purpose

AgentWeave is a collaboration framework that lets multiple AI agents (Claude, Kimi, Gemini, etc.)
work together on the same project through a shared protocol. The **AgentWeave Hub** is a
self-hosted FastAPI server with a web dashboard — agents communicate by sending messages through
it, and a host-side **watchdog** polls for new messages and auto-triggers agents.

The Hub runs in Docker. It never invokes agent CLIs directly. All agent execution happens on the
host machine via the watchdog.

---

## 2. Problem Being Solved

**Minimax** and **Zhipu GLM** have no native CLI. The common way to use them is to run the
Claude Code CLI with two overridden environment variables that redirect requests to an
OpenAI-compatible endpoint:

```bash
ANTHROPIC_BASE_URL=https://api.minimax.chat/v1 \
ANTHROPIC_API_KEY=$MINIMAX_API_KEY \
claude --resume <session_id> -p "..."
```

AgentWeave needed to:
1. Know *how* to run each agent (native CLI, claude_proxy, or manual)
2. Store the env var config per agent (base URL + which env var holds the key)
3. Track per-agent Claude session IDs for `--resume` continuity
4. Inject those env vars when the watchdog auto-pings a proxy agent

---

## 3. What Was Already Implemented (CLI side — DONE)

The following changes are already merged and working in `src/agentweave/`:

### 3a. New constants (`src/agentweave/constants.py`)

```python
RUNNER_TYPES = ["native", "claude_proxy", "manual"]

CLAUDE_PROXY_PROVIDERS = {
    "minimax": {
        "base_url": "https://api.minimax.chat/v1",
        "api_key_var": "MINIMAX_API_KEY",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_var": "ZHIPU_API_KEY",
    },
}

AGENT_RUNNER_DEFAULTS = {
    "minimax": "claude_proxy",
    "glm":     "claude_proxy",
    "cursor":  "manual",
    "windsurf": "manual",
    "copilot": "manual",
}
```

`minimax` and `glm` were also added to `KNOWN_AGENTS` and `DEFAULT_AGENT_ROLES`.

### 3b. Session model (`src/agentweave/session.py`)

Two new methods on `Session`:
- `get_runner_config(agent) → {runner, env_vars}` — reads from session data, falls back to `AGENT_RUNNER_DEFAULTS`
- `set_runner_config(agent, runner, env_vars)` — validates and persists runner config, then saves (which triggers a Hub sync)

### 3c. Validation (`src/agentweave/validator.py`)

New function `validate_runner_config(runner, env_vars) → (bool, List[str])`:
- `runner` must be in `RUNNER_TYPES`
- For `claude_proxy`: requires `ANTHROPIC_BASE_URL` (valid http/https URL) and `ANTHROPIC_API_KEY_VAR` (uppercase env var name)

### 3d. Runner helpers (`src/agentweave/runner.py`) — new file

Shared helpers used by both CLI and watchdog:
- `get_agent_env(session, agent) → Dict[str, str]` — returns `{ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY}` for proxy agents, `{}` for native/manual
- `get_missing_api_key_var(session, agent) → Optional[str]` — returns the env var name if unset
- `get_claude_session_id(agent) → Optional[str]` — reads from `.agentweave/agents/<agent>-session.json`
- `save_claude_session_id(agent, session_id)` — writes to same file
- `build_claude_proxy_cmd(agent, prompt, session_id) → List[str]` — builds `claude --output-format stream-json --verbose [--resume <id>] -p <prompt>`

### 3e. New CLI commands (`src/agentweave/cli.py`)

- `agentweave agent configure <name> [--runner ...] [--base-url ...] [--api-key-var ...]`
  - Uses built-in defaults for known providers (just `agentweave agent configure minimax` is enough)
- `agentweave agent set-session <name> <session_id>` — manually register a Claude resume ID
- `agentweave switch <agent>` — outputs eval-able `export KEY=VALUE` lines for shell env switching
- `agentweave run --agent <name>` — resolves env vars, builds relay prompt, launches Claude subprocess with env overrides
- `agentweave relay --agent <name> --run` — the `--run` flag delegates to `cmd_run`

### 3f. Watchdog update (`src/agentweave/watchdog.py`)

- `_run_agent_subprocess()` now accepts `env_override: Optional[Dict[str, str]]`
- When pinging a `claude_proxy` agent: loads session, calls `get_agent_env()`, injects the overrides into the subprocess env via `{**os.environ, **env_override}`
- If the required API key env var is not set on the watchdog process: logs a warning and skips the ping (no crash)

### 3g. Data flow

Session data (including runner config) is already synced to the Hub:
- `Session.save()` → calls `_push_session_to_hub(self._data)` → `POST /api/v1/session/sync`
- Hub stores the full session.json blob in the `ProjectSession` table
- The agents dict in the blob includes `runner` and `env_vars` for each agent

---

## 4. What Needs to Be Implemented (Hub & MCP — YOUR TASK)

The runner config is already in the Hub database (inside `ProjectSession.data`). Your task is
to **surface it** through the API, UI, and MCP server.

### 4a. Hub API — Add `runner` to AgentSummary

**File:** `hub/hub/schemas/agents.py`

Add one field to the `AgentSummary` Pydantic model:

```python
runner: str = "native"   # "native" | "claude_proxy" | "manual"
```

**File:** `hub/hub/api/v1/agents.py`

In the `list_agents()` function, the `AgentSummary(...)` constructor call already reads `role`
and `yolo` from `agent_meta`. Add `runner` the same way:

```python
# Existing lines (for reference):
role=agent_meta.get("role"),
yolo=bool(agent_meta.get("yolo", False)),

# Add this:
runner=agent_meta.get("runner", "native"),
```

`agent_meta` is `session_agents_meta.get(agent_name, {})` — it's the dict for that agent from
`session.json`, which already has `runner` when set by `agentweave agent configure`.

---

### 4b. Hub UI — runner badge in AgentCard

**File:** `hub/ui/src/api/agents.ts`

Add to the `AgentSummary` TypeScript interface:
```typescript
runner?: string   // "native" | "claude_proxy" | "manual"
```

**File:** `hub/ui/src/components/agents/AgentCard.tsx`

The card already shows a `role` badge (principal/delegate/collaborator) and a `yolo` bolt icon.
Add a runner badge for non-native agents, rendered alongside those existing badges:

- `runner === "claude_proxy"` → show a small styled chip/badge with text **"proxy"**
  - Suggested color: amber/orange tint (distinct from the role badge)
- `runner === "manual"` → show **"manual"** badge in grey
- `runner === "native"` or undefined → render nothing (keep it clean)

Match the existing badge styling in the file (look at how the `role` badge is rendered and
follow the same pattern).

---

### 4c. Hub UI — proxy warning in trigger panel

**File:** `hub/ui/src/components/agents/AgentMessageSender.tsx`

When the user opens the trigger/send panel for an agent that has `runner === "claude_proxy"`,
show an informational warning banner above the input form. Suggested text:

> ⚠ This is a proxy agent (runs via Claude CLI with custom env vars).
> Triggering it requires your watchdog to be running with the appropriate API key exported
> (e.g. `export MINIMAX_API_KEY=...` before `agentweave start`).

The `AgentSummary` (including `runner`) for the selected agent is available from the `useAgents()`
cache that the parent `AgentsPage` already loads. Thread it down as a prop or read it from the
cache inside this component (whichever fits the existing data-flow pattern in the file).

---

### 4d. MCP server — `get_agent_config` tool

**File:** `hub/hub/mcp_server.py`

Add an 11th MCP tool. The MCP server has a `_hub_request(method, path, body, params)` helper
that makes authenticated REST calls to the Hub. Use it to call the agents and session endpoints:

```python
@mcp.tool()
def get_agent_config(agent: str) -> Dict[str, Any]:
    """Get runner configuration for an agent.

    Returns runner type and, for claude_proxy agents, the base URL and the
    name of the env var that holds the API key. Actual API key values are
    never stored or returned.

    Args:
        agent: Agent name (e.g. "minimax")

    Returns:
        Dict with 'runner', and for claude_proxy agents also 'base_url' and
        'api_key_var'. Returns {'error': '...'} if agent not found.
    """
    try:
        agents = _hub_request("GET", "/agents")
        match = next((a for a in agents if a.get("name") == agent), None)
        if not match:
            return {"error": f"Agent '{agent}' not found"}

        result: Dict[str, Any] = {
            "name": agent,
            "runner": match.get("runner", "native"),
        }

        # For proxy agents, include connection details from the full session blob
        if result["runner"] == "claude_proxy":
            session = _hub_request("GET", "/session/sync")
            agent_cfg = session.get("data", {}).get("agents", {}).get(agent, {})
            env_vars = agent_cfg.get("env_vars", {})
            result["base_url"] = env_vars.get("ANTHROPIC_BASE_URL", "")
            result["api_key_var"] = env_vars.get("ANTHROPIC_API_KEY_VAR", "")

        return result
    except RuntimeError as e:
        return {"error": str(e)}
```

Place it after the existing `get_status` tool and before the human-interaction tools block.

---

## 5. Key Architecture Facts (to avoid mistakes)

- **Hub never invokes CLIs** — it's Docker-only. All CLI execution is on the host via watchdog.
- **ProjectSession.data** is the single source of truth for agent config in the Hub. It's the
  full `session.json` blob, synced by `agentweave start` (watchdog) via `POST /api/v1/session/sync`.
- **`runner` and `env_vars` are already in `ProjectSession.data`** — you just need to read them.
- **API key values are never stored** — only the env var *name* (e.g. `"MINIMAX_API_KEY"`).
- **`GET /api/v1/session/sync`** returns `{"data": {... full session.json ...}, "synced_at": "..."}`.
- **`GET /api/v1/agents`** returns `List[AgentSummary]` — after your change, each item will
  include the new `runner` field.
- The `_hub_request` helper in `mcp_server.py` reads `HUB_URL`, `HUB_API_KEY`, and
  `HUB_PROJECT_ID` from environment at call time — no setup needed in your new tool.

---

## 6. File Summary

| File | Change |
|------|--------|
| `hub/hub/schemas/agents.py` | Add `runner: str = "native"` to `AgentSummary` |
| `hub/hub/api/v1/agents.py` | Read `runner` from `agent_meta` in `list_agents()` |
| `hub/ui/src/api/agents.ts` | Add `runner?: string` to `AgentSummary` interface |
| `hub/ui/src/components/agents/AgentCard.tsx` | Add proxy/manual runner badge |
| `hub/ui/src/components/agents/AgentMessageSender.tsx` | Add proxy warning banner |
| `hub/hub/mcp_server.py` | Add `get_agent_config()` tool (11th tool) |

---

## 7. Verification Steps

```bash
# 1. On the host: configure minimax and start watchdog
agentweave init --project "Test" --agents claude,minimax
agentweave agent configure minimax          # uses built-in defaults
agentweave transport setup --type http \
  --url http://localhost:8000 \
  --api-key aw_live_... \
  --project-id proj-default
agentweave start                            # watchdog syncs session → Hub

# 2. Check Hub API includes runner
curl -s -H "Authorization: Bearer aw_live_..." \
  http://localhost:8000/api/v1/agents | python -m json.tool
# → minimax entry should have: "runner": "claude_proxy"

# 3. Check MCP tool via Hub session (confirm data is there)
curl -s -H "Authorization: Bearer aw_live_..." \
  http://localhost:8000/api/v1/session/sync | python -m json.tool
# → agents.minimax should have runner, env_vars

# 4. Open dashboard → Agents tab
# → minimax card should show a small "proxy" badge

# 5. Click minimax → Message Sender tab
# → Should see the proxy warning banner

# 6. Test MCP get_agent_config tool in your MCP client
# → Should return {name: "minimax", runner: "claude_proxy",
#    base_url: "https://api.minimax.chat/v1", api_key_var: "MINIMAX_API_KEY"}
```

---

## 8. Notes

- Do not change any CLI files (`src/agentweave/`) — that work is done.
- Do not add a new DB table or new API endpoints beyond what's described above.
  The data is already in the DB; we're just reading it differently.
- Keep the `AgentMessageSender` warning informational only — do not block sending.
- After editing UI files, rebuild with `cd hub/ui && npm run build` so the Docker image
  picks up the changes.
