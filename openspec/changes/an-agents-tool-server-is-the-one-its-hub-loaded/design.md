# Design — an agent's tool server is the one its Hub loaded

## Operator review, 2026-09-24

Adversarial Opus review: `spec-queue/tracks/reviews/B11-2026-09-24.md` §1, **APPROVE WITH FIXES**.
The operator decided F354 as recommended (pin, D5 option a) and, on the review's MEDIUM finding,
that **the pin lives under `~/.agentweave/hub/tool-server/<digest>/`**, not in the shared temp
directory. Applied here:

- **MEDIUM (security), fixed in D1a.** `tempfile.gettempdir()` is `/tmp` on native Linux, writable
  by every local user: one could pre-create `agentweave-tool-server/<digest>/` and swap the file
  between D2's check and the runner's spawn (a TOCTOU race), or simply own the directory so every
  MCP turn of another user's Hub answers 409. The pin now lives under the Hub user's own home.
- **LOW, fixed in tasks 4.1-4.2.** `.claude/rules/mcp-server.md` says *"The operator's `:8000` Hub
  spawns this file fresh on every agent turn…"*, which this change makes false; a task rewrites it,
  and another checks the `DEAD-ENDS.md` entries that mention `mcp_server.py`.
- **LOW, decided in D7.** Old digest directories are pruned at startup once untouched for seven
  days; they are not pruned unconditionally, because another Hub on the machine may be using one.

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
| The Hub's own home-relative directory is `~/.agentweave/hub` (the CLI's `HUB_DIR`); the Hub process computes it as `Path.home() / ".agentweave" / "hub"` and knows no profile | `src/agentweave/cli.py:242`; `hub/hub/config.py:25` |
| `agentweave reset` deletes a profile's `data/` directory, the `.env`, pid and log files, never a sibling directory of `HUB_DIR` | `src/agentweave/cli.py:1368` onward (`_hub_profile_data_dir`, `HUB_DIR / ".env"`) |

Because `mcp_server.py` is self-contained, a byte-for-byte copy anywhere on disk is the same
program. That is what makes a pin a copy and not a packaging change.

## D1 — Read once at import, write to a content-addressed path

`hub/hub/tool_server.py`:

```python
class ToolServerPin:
    def __init__(self, source: Path, root: Path | None = None) -> None:
        self._bytes = source.read_bytes()          # once; the Hub's start
        self.digest = hashlib.sha256(self._bytes).hexdigest()[:16]
        self._root = root or pin_root()            # D1a: ~/.agentweave/hub/tool-server
        self._target = self._root / self.digest / "mcp_server.py"

    def path(self) -> Path:                        # every spawn; may raise OSError
        ...  # D2

    def prune_stale(self, max_age: timedelta = timedelta(days=7)) -> list[Path]:
        ...  # D7; called once from the lifespan

def pin_root() -> Path: return Path.home() / ".agentweave" / "hub" / "tool-server"
PIN = ToolServerPin(Path(__file__).parent / "mcp_server.py")
def pinned_server_path() -> Path: return PIN.path()
```

- **At import**, because the Hub imports its modules when it starts and that is the moment the rest
  of its Python is fixed. `main.py`'s lifespan also calls `pinned_server_path()` once, so the file
  exists before the first turn and the startup log names it. A failure there is logged, not fatal:
  D2 retries on every spawn, and a Hub that cannot write under its own home has larger problems
  that the refusal in D3 will name.
- **Content-addressed**, so two Hubs of different versions on one machine (`:8000` and a trial Hub)
  never overwrite each other's server, and two of the same version share one file.
- **Outside the repository**, deliberately. Inside it, the file would show in `git status`, be
  swept by `git add -A`, and sit inside some agent's workspace.

## D1a — Where the pin lives: under the Hub user's home, not the shared temp directory

`pin_root()` returns `Path.home() / ".agentweave" / "hub" / "tool-server"`, the same home-relative base the
CLI calls `HUB_DIR` (`src/agentweave/cli.py:242`) and `hub/hub/config.py:25` already computes for the
default database. The directory is created with `mkdir(parents=True, exist_ok=True, mode=0o700)`.

- **Why not `tempfile.gettempdir()`** (R1's choice, review §1 MEDIUM): on native Linux that is
  `/tmp`, shared by every local user. Another user can pre-create
  `/tmp/agentweave-tool-server/<digest>/` (the digest is public: it is a hash of a published file),
  and then either swap `mcp_server.py` between D2's byte check and the runner CLI's spawn, running
  their code with this user's credentials and run token (a TOCTOU race), or leave the directory
  unwritable, so every MCP turn of this user's Hub answers D3's 409. Under the user's home, only
  that user (or root) can write, so D2's check and the spawn see the same file.
- **Not per `--profile`.** The Hub process is told its database, not its profile (`config.py`), and
  a content-addressed file is the same program whichever profile's Hub wrote it, so two profiles, or
  `:8000` and a trial Hub, share one directory safely. `agentweave reset` never touches it.
- **Docker mode:** the container's home is the container's; the pin is recreated at each start, which
  is what D1 wants.
- The residual race (another process of the *same* user rewriting the file between check and spawn)
  is out of scope: that user can already edit the checkout.

## D2 — A spawn verifies before it names

`path()` returns the target when it exists and its bytes equal `self._bytes` (and refreshes its
mtime for D7). Otherwise it creates the directory (D1a) and writes
`self._bytes` to a sibling temp file and `os.replace`s it onto the target, then returns it. So a cleaner, a
manual delete, or another process writing a different version into the same digest directory (which
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

## D7 — Old pinned copies: pruned at startup once stale

Each Hub version leaves one ~100 KB directory. `prune_stale()` runs once in the lifespan, right after
the pin is written, and removes every sibling `<digest>/` directory under the pin's root whose
`mcp_server.py` has not been modified for seven days, never the Hub's own digest. `path()` refreshes
its target's mtime (`os.utime`) on every spawn, so a directory in use by any Hub on the machine stays
fresh.

**Why not prune every other digest unconditionally:** two Hubs of different versions (`:8000` and a
trial Hub) run at once. Deleting the other Hub's directory between its D2 check and its runner's
spawn would hand that runner a missing file, a server that fails to start, which is F340's invisible
failure. D2 would heal it on the next spawn, but not for the turn it hit. Seven days of no spawns
means no Hub has used that version for a week.

A prune failure (`OSError`) is logged and ignored: stale copies cost disk, not correctness.

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
- R3 2026-09-24: traced the launch end to end, fresh. The Hub never runs the server itself: it
  hands `[sys.executable, <path>]` to the runner CLI (Claude `--mcp-config`,
  `runner_commands.py:250-260`; Codex `config.mcp_servers` per `thread/start`,
  `codex_appserver.py:969-972`), and that CLI spawns a new Python per turn, which reads the file
  **at that spawn**. So the path in `mcp_command` is exactly what a live agent loads, and pinning it
  changes every turn spawned after the pinning Hub's start; a turn already running keeps the process
  it has, pinned or not. `main.py:22` imports `agent_trigger` at module top, so task 2.2's module
  import takes the pin at start. **One difference a copy makes, checked:** Python puts the script's
  own directory first on `sys.path`, so today `hub/hub/` is importable by the server and after the
  pin the digest directory is. No `hub/hub/*.py` shares a name with a standard-library module
  (checked against `sys.stdlib_module_names`) and the server imports nothing else from its
  directory, so the program is the same. **Residual, not pinned:** `fastmcp` and the standard
  library still load from the Hub's interpreter at each spawn, so a `pip install` into that
  environment reaches the next turn; that is an environment change, not a checkout edit. No
  disagreement; no edit beyond this log.
- Operator review 2026-09-24 (`spec-queue/tracks/reviews/B11-2026-09-24.md` §1): pin moved from the
  temp directory to `~/.agentweave/hub/tool-server/<digest>/` (D1a); stale-digest pruning decided
  (D7); tasks 1.8-1.10 and 4.1-4.2 added. Re-verified on `09127ba`: every Context-table citation
  holds (`agent_trigger.py:1110-1118`, `:1141-1144`, `run_id` at `:1176`; `turn_scheduler.py:424`;
  `runner_commands.py:250-259`; `codex_appserver.py:652-662`, `:969-972`; `main.py:22`;
  `test_agent_trigger.py:747`, `:972`; `test_mcp_server_stdio_surface.py:29`; `mcp_server.py` is
  99,949 bytes).
