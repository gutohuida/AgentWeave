# One Hub, wherever it's launched from — and a window of its own

## Why

The operator asked for two things that turn out to be one change
(`openspec/explorations/2026-08-16-desktop-app-global-state.md`, Section 1): *"agentweave should be
global... if I ran agentweave from different folders it creates a different agentweave which is
weird. Now that I want it to be a full app opening always restore the same state"* and *"I also want
a full app experience with agentweave no more opening on the browser."* A desktop app that opens a
different database depending on which folder it was launched from would be incoherent, so the shell
and the instance-state fix are specified together.

**The global-state bug is narrower than it first looked.** The exploration re-diagnosed it against
the actual call paths rather than the single `hub/hub/config.py:9` line first blamed for it:
`agentweave hub-start` (native mode, no flags — the command a `pip install agentweave-ai` user
actually runs) has been global since commit `ab53cf4` (2026-08-03): `_hub_native_start`
(`src/agentweave/cli.py:664`) computes an absolute `Path.home() / ".agentweave" / "hub" / "data" /
"agentweave.db"` and sets `DATABASE_URL` in the environment *before* importing `hub.main`, so
`config.py`'s relative default never fires on that path. The bug survives in exactly two other
places, both confirmed live rather than assumed: (1) anyone who imports `hub.main` without going
through the CLI — e.g. `uvicorn hub.main:app` run directly, which is this autonomous run's own
`restart_command` — inherits the relative default and gets whatever directory the shell happened to
be in; (2) `hub/docker-compose.yml` has no top-level `name:` key, so Docker Compose derives its
project-name prefix (and therefore the `hub-data` volume's real name) from the launch directory's
basename, giving a different volume — a different database — per directory even though the container
itself resolves its relative path consistently.

**The desktop app is the other half.** `_open_app_window` (`cli.py:634`) already opens the Hub in a
chromeless `chrome --app=<url>` window today via the existing `--app` flag — a real, zero-dependency
floor, but not a true desktop shell: the dock/taskbar icon and process are the browser's, not
AgentWeave's, and there is no window if the operator has no Chrome/Edge installed. The exploration
compared Electron, Tauri/PyTauri, and pywebview against this run's standing constraint (no new
language toolchain) and recommended pywebview: pure `pip install`, no Rust or Node, and it already
pairs with a FastAPI-backend-plus-built-frontend in exactly AgentWeave's shape.

## What Changes

- **`hub/hub/config.py`'s `database_url` default becomes the same absolute, home-relative path native
  mode already computes**, closing the two remaining holes (direct `uvicorn hub.main:app`, and
  belt-and-braces for any future caller that imports `hub.main` without going through the CLI). No
  behavior change for anyone who has only ever used `agentweave hub-start`.
- **`hub/docker-compose.yml` gets a top-level `name: agentweave`**, making Compose's project name —
  and therefore the `hub-data` volume it creates — independent of the directory `docker compose up`
  was run from.
- **An explicit migration decision** for the two populations this leaves behind (`design.md` D4):
  data already sitting at a project-relative path or a directory-prefixed Docker volume from before
  this fix.
- **`pywebview` as an optional extra** (`agentweave-ai[app]`), not a base dependency — the CLI's
  `dependencies = []` stance in `pyproject.toml` is preserved; installing it is the operator's choice.
- **`--app` opens a real desktop window when pywebview is installed**, falling back to today's
  chromeless-browser behavior when it is not (`design.md` D3 covers the threading/process model this
  requires — pywebview's event loop must own the calling thread, which changes how `--app` composes
  with `--no-detach`).
- **Bare `agentweave` continues to register the invocation directory as a project** (per
  `app-lifecycle`'s existing "Bare invocation is the only entry point" requirement) — nothing about
  per-folder *project* registration changes; only the Hub's own single-instance state (database,
  bootstrap credentials, one running process) becomes launch-path-independent, matching
  `CLAUDE.md`'s existing "Local multi-project boundary" section.

## Impact

**Behavior** — one AgentWeave Hub instance regardless of whether it is launched via `agentweave
hub-start`, direct `uvicorn`, or Docker Compose, from any directory. `agentweave --app` (or
`hub-start --app`) opens a dedicated window with its own OS taskbar/dock presence when `pywebview` is
installed.

**Dependencies** — one new *optional* dependency (`pywebview`) on the CLI distribution only; the Hub
distribution (`agentweave-hub`) is untouched. No change to either package's required dependencies.

**Schema** — none. The database's location changes for two specific pre-existing populations
(`design.md` D4); its schema does not.

**Process model** — `--app` with `pywebview` installed changes from "spawn a detached window process
and return" to "block the invoking process in the window's event loop" (`design.md` D3). This is a
real behavior change for scripts that currently call `agentweave hub-start --app` and expect it to
return promptly; recorded, not hidden.

## Non-Goals

- **Not Tauri or PyTauri.** Best-specced option in the exploration's own comparison, but needs a Rust
  toolchain, which this run's standing constraint forbids installing. Recorded in `decisions_for_user`
  as the cost of that constraint, not rejected on merit — re-evaluate first if the constraint lifts.
- **Not code signing or auto-update.** Real, unresearched costs the exploration named and explicitly
  deferred (Section 5); out of scope for a shell/instance-state fix.
- **Not packaging pywebview's Linux GTK/Qt system dependency.** Documented as a requirement
  (`design.md` D5), not vendored or silently worked around.
- **Not changing per-folder project *registration*.** `app-lifecycle`'s "Invocation from another
  directory reuses the instance" scenario is precedent, not something this change touches — a second
  directory still becomes a second project in the same instance; it was never a second instance under
  `hub-start`, and this change does not alter that.
- **Not relocating existing per-user data to a more OS-idiomatic path** (e.g. `platformdirs`'s
  `%LOCALAPPDATA%`/`~/Library/Application Support`/XDG placement). `Path.home() / ".agentweave"`
  already resolves correctly on every OS and needs no new dependency; a future proposal can weigh
  that refinement against the CLI's zero-runtime-dependency stance on its own.
