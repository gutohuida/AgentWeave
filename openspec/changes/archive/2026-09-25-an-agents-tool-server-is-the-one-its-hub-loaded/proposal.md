# Proposal — an agent's tool server is the one its Hub loaded

**Round 1, 2026-09-24** (bundle B11, `spec-queue/tracks/B11.md`). Finding: **F354 (B)**. Re-verified
on `ce086b6` (the bundle worktree's HEAD, one commit past `404c7d5`, which touched no code).
**Nothing here is implemented yet.** Amended 2026-09-24 after the operator's review
(`spec-queue/tracks/reviews/B11-2026-09-24.md` §1): the pin lives under the Hub user's home, and
stale copies are pruned.

## Why

Every Hub-spawned run that gets the Hub's own MCP server is handed a command that names the server
**by its path in the checkout the Hub was started from**:

```python
# hub/hub/api/v1/agent_trigger.py:1141-1144
mcp_command = None
if access_path == "mcp":
    canonical_server = Path(__file__).resolve().parents[2] / "mcp_server.py"
    mcp_command = [sys.executable, str(canonical_server)]
```

The same list reaches the Claude argv (`runner_commands.py:250-259`, `--mcp-config`) and Codex's
app-server `config.mcp_servers` (`codex_appserver.py:969-972`). So the server a run gets is whatever
`hub/hub/mcp_server.py` holds **at the moment that run spawns**, not what the Hub loaded.

Every other Python file the Hub runs is fixed when the Hub starts. `mcp_server.py` is the one source
file re-read from disk on every turn (`grep -rn "sys.executable" hub/hub` finds this site, the
folder dialog's inline `-c` script, and a comment; nothing else spawns a repository file). On
`:8000`, which runs this checkout by intent (CLAUDE.md), that means:

1. **Uncommitted edits reach live agents mid-edit.** F354's observation: at 22:31 UTC on
   2026-09-13 the night window had uncommitted edits to `mcp_server.py` while the operator's flow
   fired a turn every five minutes.
2. **Committed edits reach live agents before the routes they call exist.** A branch moving on the
   checkout (a commit, a fast-forward, a checkout) changes the file at once. A new tool that calls a
   route the running Hub does not have yet fails at the agent's first call. B12's
   `a-specification-is-read-in-results-that-fit` spends its design D5 on exactly this skew, and its
   IMPL was held on 2026-09-14 because of it (F363).
3. **A broken edit is a server that fails to start**, which the harness reports as `failed` in its
   `init` line and the Hub does not record (F340). The run is still told it has the MCP tool surface.

## What Changes

- **The Hub pins its tool server when it starts** (design D1). A new module,
  `hub/hub/tool_server.py`, reads `mcp_server.py`'s bytes once, at import, and writes them to a
  content-addressed file outside the repository, under
  `~/.agentweave/hub/tool-server/<digest>/` (design D1a): the Hub user's own directory, not the
  shared temp directory another local user could pre-create. Every spawn names that file.
- **A spawn checks the pinned file before naming it**, and rewrites it from the bytes held in memory
  if it has gone or changed (design D2). A cleaner or a manual delete cannot change what a run gets.
- **Stale pinned copies are pruned at startup** once no Hub has spawned them for seven days
  (design D7); a copy another running Hub is using is never removed.
- **A pin that cannot be written refuses the turn with a sentence**, through the same path the
  canonical-context file already uses (`agent_trigger.py:1110-1118`, a `TriggerAgentError` 409).
  The input stays queued with that reason (`turn_scheduler.py:424` onward). It never falls back to
  the checkout's file, because the fallback is the defect (design D3).
- **The served-surface check spawns the pinned file** (design D4), so the requirement *"One tool
  surface, configured automatically"* keeps verifying the program agents actually run.

No migration, no API shape, no UI, no bundle. `mcp_server.py` itself is not edited.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-tool-surface`: a new requirement, *The tool server a run is given is the one its Hub
  loaded*.

## Impact

- `hub/hub/tool_server.py` (new), `hub/hub/api/v1/agent_trigger.py` (`:1141-1144` only),
  `hub/hub/main.py` (lifespan: pin at start, log where, prune stale copies).
- `.claude/rules/mcp-server.md`: its line that `:8000` spawns this file fresh on every turn is
  rewritten (task 4.1); the `DEAD-ENDS.md` entries naming `mcp_server.py` are checked (task 4.2).
- `hub/tests/`: a new `test_tool_server_pin.py`; `test_agent_trigger.py:747` and `:972` gain an
  assertion; `test_mcp_server_stdio_surface.py:29` spawns the pinned path.
- **Takes effect on a Hub only once that Hub restarts onto it.** For `:8000` that is the operator's
  call. Until then, `:8000` keeps spawning its checkout's file.
- **Releases B12's F363** from the skew argument: once `:8000` runs this, an edit to
  `mcp_server.py` reaches its agents on the same restart as the routes it calls.
