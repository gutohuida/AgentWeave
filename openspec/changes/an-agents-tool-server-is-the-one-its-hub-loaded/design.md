# Design — an agent's tool server is the one its Hub loaded

**Built on the recommended answer to B11's F354 question** (ROUNDS.md D13, *"live agents run MCP
from the working tree"*): **pin the server the Hub loaded.** If the operator answers otherwise, this
change is withdrawn. The alternatives, and why each loses, are in D5.

## Context — measured on `ce086b6`

| Fact | Where |
|---|---|
| The spawn names the checkout's file, resolved from `agent_trigger.py`'s own location | `hub/hub/api/v1/agent_trigger.py:1141-1144` |
| Claude receives it as `--mcp-config` `{"command": ..., "args": [...]}` | `hub/hub/runner_commands.py:250-259` |
| Codex app-server receives the same list as `config.mcp_servers.<name>` | `hub/hub/codex_appserver.py:652-662`, `:969-972` |
| `mcp_server.py` imports only the standard library and `fastmcp` | `grep -n "^import\|^from\|^    from" hub/hub/mcp_server.py`: `contextlib json os re time urllib.* typing`, and `from fastmcp import FastMCP` at `:19` |
| It never reads its own location or a sibling file | `grep -n "__file__\|sys.path" hub/hub/mcp_server.py` finds nothing; `__name__` only at `:2081` |
| No other repository file is spawned per turn | `grep -rn "sys.executable" hub/hub --include=*.py`: this site, `native_dialog.py:146` (an inline `-c` script held in memory), `subprocess_windows.py:92` (a comment) |
| The context file already has a write-or-refuse precedent | `agent_trigger.py:1110-1118`: `OSError` → `TriggerAgentError(409, "Could not materialize canonical context for {agent}: {exc}")` |
| A `TriggerAgentError` keeps the input queued and records its sentence | `hub/hub/turn_scheduler.py:424` onward (rollback, re-read, `waiting_reason` written) |
| The served-surface test spawns the checkout's file directly | `hub/tests/test_mcp_server_stdio_surface.py:29` |

Because `mcp_server.py` is self-contained, a byte-for-byte copy anywhere on disk is the same
program. That is what makes a pin a copy and not a packaging change.

## D1 — Read once at import, write to a content-addressed path

`hub/hub/tool_server.py`:

```python
class ToolServerPin:
    def __init__(self, source: Path) -> None:
        self._bytes = source.read_bytes()          # once; the Hub's start
        self.digest = hashlib.sha256(self._bytes).hexdigest()[:16]
        self._target = Path(tempfile.gettempdir()) / "agentweave-tool-server" / self.digest / "mcp_server.py"

    def path(self) -> Path:                        # every spawn; may raise OSError
        ...  # D2

PIN = ToolServerPin(Path(__file__).parent / "mcp_server.py")
def pinned_server_path() -> Path: return PIN.path()
```

- **At import**, because the Hub imports its modules when it starts and that is the moment the rest
  of its Python is fixed. `main.py`'s lifespan also calls `pinned_server_path()` once, so the file
  exists before the first turn and the startup log names it. A failure there is logged, not fatal:
  D2 retries on every spawn, and a Hub that cannot write to its temp directory has larger problems
  that the refusal in D3 will name.
- **Content-addressed**, so two Hubs of different versions on one machine (`:8000` and a trial Hub)
  never overwrite each other's server, and two of the same version share one file.
- **Outside the repository**, deliberately. Inside it, the file would show in `git status`, be
  swept by `git add -A`, and sit inside some agent's workspace.

## D2 — A spawn verifies before it names

`path()` returns the target when it exists and its bytes equal `self._bytes`. Otherwise it writes
`self._bytes` to a sibling temp file and `os.replace`s it onto the target, then returns it. So a temp
cleaner, or another process writing a different version into the same digest directory (which
SHA-256 makes practically impossible), cannot change what a run is given. The comparison costs one
read of an ~100 KB file (99,949 bytes today) per spawn. A spawn already writes the whole context file, so this does not
change the order of cost.

A run already started has loaded its script, so deleting or replacing the file under a live server
changes nothing for that run.

## D3 — A pin that cannot be written refuses; it never falls back

```python
if access_path == "mcp":
    try:
        mcp_command = [sys.executable, str(pinned_server_path())]
    except OSError as exc:
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            f"Could not materialize the tool server for {agent}: {exc}",
        ) from exc
```

**What the route returns when this raises:** exactly what it returns for the context-file failure
three lines above it, since it is the same exception on the same path. On the scheduler path the
input stays queued and the sentence is recorded as its `waiting_reason` (`turn_scheduler.py:424`
onward). No `Run` row exists yet at this point (`run_id` is minted at `:1176`, after `build_command`).

**Why not fall back to the checkout's file:** the fallback is the defect. A silent fallback would
make "pinned" true only on machines where nothing goes wrong, and the operator could not tell which
kind of turn they got.

## D4 — The served-surface check spawns what agents spawn

`agent-tool-surface` *"One tool surface, configured automatically"* requires verification to *"spawn
the server the way the Hub spawns it"*. `test_mcp_server_stdio_surface.py:29` spawns
`hub/hub/mcp_server.py` directly. It changes to spawn `pinned_server_path()`. The two files are
byte-identical in a test process, so the test's verdict does not change; what changes is that the
test now fails if the pin ever stops being a faithful copy.

## D5 — The options, and why this one

| Option | What it would break | What it releases |
|---|---|---|
| **(a) Pin at start (this change)** | Nothing on a clean install: the copy is the same program. A developer editing `mcp_server.py` must restart the Hub to try it, exactly as for every other Hub file. | Uncommitted edits stop reaching live agents; tools and routes change on one restart; F363 can build on `mcp_server.py` without a skew analysis. |
| (b) A rule: never edit `mcp_server.py` in the checkout `:8000` runs | Nothing in code. It blocks every tool change on the one file most changes touch, and it is a rule the product cannot check. F363 has been blocked on it since 2026-09-14. | Nothing structural. |
| (c) Run `:8000` from an installed copy or a separate worktree | CLAUDE.md's *"`:8000` … runs this checkout by intent"*. The operator chose that arrangement, and its other costs (restart migrations, bundle on reload) are listed and accepted. | The hazard, for `:8000` only; any other Hub run from a checkout keeps it. |
| (d) Spawn `python -m hub.mcp_server` | Nothing, and it fixes nothing: the module is still read from the working tree at spawn. | — |

(a) is the only option that makes the Hub consistent with itself: its routes and its tool server
change together, on the same event.

## D6 — Interactions inside B11

- **F340** (parked, confirmed 2026-09-21): the Hub records nothing when its own server fails to
  start. This change removes this checkout's likeliest cause of that failure, a half-written
  `mcp_server.py`. F340 stays parked; nothing here depends on it.
- **F21** (B11 recommends a probe, not retirement): the tool surface's *size* is F21's question; its
  *source file* is this one's. They do not interact.
- **B12 / F363**: see the proposal's Impact. Recommended order: this change's IMPL, then the
  operator's `:8000` restart, then F363's `mcp_server.py` half. B12's D5 shows that F363 can also ship
  first without breaking anything, so this is a preference, not a gate.

## Open questions

None for the operator beyond the decision this design is built on.

## Round log

- R1 2026-09-24: written.
- R2 2026-09-24: re-read the spawn (`agent_trigger.py:1141-1144`), the context-file refusal
  (`:1110-1118`), the only spawn sites (`grep "mcp_server"` in `hub/hub` and `src/`), and
  `mcp_server.py`'s self-containment (no `__file__`/`sys.path`). **Disagreed (1):** task 2.2's
  `from … import pinned_server_path` would make task 1.6's patch miss; now a module import. **Nuance
  (no edit to D1's logic):** "every other file is fixed at start" holds for module-level imports; the
  Hub also imports some modules lazily inside functions, which load on first call. The pin's own
  guarantee needs only that `tool_server` is imported at module top by `agent_trigger` (task 2.2)
  and called in the lifespan (2.3). **Residual, out of scope:** `src/agentweave/mcp/server.py` imports
  `hub.mcp_server` for a non-Hub-spawned client; the pin covers Hub-spawned runs only. Checked
  against B12 (F363) and B4: both order against this pin as a preference, not a gate; consistent.
