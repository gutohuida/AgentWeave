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
the actual call paths rather than the single `hub/hub/config.py:9` line first blamed for it: bare
`agentweave` (native mode, no flags — the only entry point `create_parser()` exposes, and the
command a `pip install agentweave-ai` user actually runs) has been global since commit `ab53cf4`
(2026-08-03): `_hub_native_start`
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
chromeless `chrome --app=<url>` window today whenever app mode is on — which, since `main()`
unconditionally forces `parsed_args.app = True` for bare invocation (`cli.py:1126`), the only entry
point this CLI has, means *every* normal launch, not an opt-in flag. That's a real, zero-dependency
floor, but not a true desktop shell: the dock/taskbar icon and process are the browser's, not
AgentWeave's, and there is no window if the operator has no Chrome/Edge installed. The exploration
compared Electron, Tauri/PyTauri, and pywebview against this run's standing constraint (no new
language toolchain) and recommended pywebview: pure `pip install`, no Rust or Node, and it already
pairs with a FastAPI-backend-plus-built-frontend in exactly AgentWeave's shape.

## What Changes

- **`hub/hub/config.py`'s `database_url` default becomes the same absolute, home-relative path native
  mode already computes**, closing the two remaining holes (direct `uvicorn hub.main:app`, and
  belt-and-braces for any future caller that imports `hub.main` without going through the CLI). No
  behavior change for anyone who has only ever used bare `agentweave` (native mode).
- **`hub/docker-compose.yml` gets a top-level `name: agentweave`**, making Compose's project name —
  and therefore the `hub-data` volume it creates — independent of the directory `docker compose up`
  was run from.
- **An explicit migration decision** for the two populations this leaves behind (`design.md` D4):
  data already sitting at a project-relative path or a directory-prefixed Docker volume from before
  this fix.
- **`pywebview` as an optional extra** (`agentweave-ai[app]`), not a base dependency — the CLI's
  `dependencies = []` stance in `pyproject.toml` is preserved; installing it is the operator's choice.
- **App mode opens a real desktop window when pywebview is installed**, falling back to today's
  chromeless-browser behavior when it is not (`design.md` D3 covers the threading/process model this
  requires — pywebview's event loop must own the calling thread). App mode is not an opt-in flag: it
  is forced on for bare invocation, the CLI's only entry point, and for the Docker branch
  (`--docker`/`--local`) as well, so this is a change to the default behavior of every normal launch,
  not a feature callers must ask for. **One named exception:** the foreground (`--no-detach`) start
  path keeps today's browser fallback unconditionally, because its main thread is already committed
  to running the backend server in the foreground — see `design.md` D3.
- **Bare `agentweave` continues to register the invocation directory as a project** (per
  `app-lifecycle`'s existing "Bare invocation is the only entry point" requirement) — nothing about
  per-folder *project* registration changes; only the Hub's own single-instance state (database,
  bootstrap credentials, one running process) becomes launch-path-independent, matching
  `CLAUDE.md`'s existing "Local multi-project boundary" section.
- **A `--profile <name>` flag names a second, deliberate instance** (`design.md` D6, added
  2026-08-17 to resolve amendment A3), so the fix above does not leave "exactly one instance is
  reachable" as the new trap it replaces "a different instance per launch directory" with. A profile
  carries its own database (`~/.agentweave/hub/profiles/<name>/agentweave.db`) and its own PID file;
  the default profile is unchanged and unaffected. `reset --profile <name>` scopes reset's blast
  radius to one profile instead of leaving it ambiguous once a second instance exists.

## Impact

**Behavior** — one AgentWeave Hub instance regardless of whether it is launched via bare
`agentweave`, direct `uvicorn`, or Docker Compose, from any directory. Bare `agentweave` (and
`agentweave --docker`/`agentweave --local`) opens a dedicated window with its own OS taskbar/dock
presence when `pywebview` is installed — the default experience of the CLI's one entry point, not an
opt-in.

**Dependencies** — one new *optional* dependency (`pywebview`) on the CLI distribution only; the Hub
distribution (`agentweave-hub`) is untouched. No change to either package's required dependencies.

**Schema** — none. The database's location changes for two specific pre-existing populations
(`design.md` D4); its schema does not.

**Process model** — app mode with `pywebview` installed changes from "spawn a detached window process
and return" to "block the invoking process in the window's event loop" (`design.md` D3). Because app
mode is forced on for the CLI's one and only entry point (`cli.py:1126`) and for its Docker branch,
this is a real behavior change to the **default** experience of every normal launch — not, as the
`--app` framing might suggest, something only scripts that opt into a flag would notice. Recorded,
not hidden.

**Testability** — the native desktop window (D3) cannot be driven by Playwright; this is accepted, not
solved, and D3 now states the binding constraint (a thin, logic-free shell) that keeps that gap
narrow rather than open-ended (`design.md` D3, "Testability, resolved").

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
  bare `agentweave`, and this change does not alter that.
- **Not relocating existing per-user data to a more OS-idiomatic path** (e.g. `platformdirs`'s
  `%LOCALAPPDATA%`/`~/Library/Application Support`/XDG placement). `Path.home() / ".agentweave"`
  already resolves correctly on every OS and needs no new dependency; a future proposal can weigh
  that refinement against the CLI's zero-runtime-dependency stance on its own.
- **Not a Docker profile-equivalent.** D6 (`--profile`) is CLI-only; `docker compose up` still
  produces the one instance D2 already pins. A per-profile `COMPOSE_PROJECT_NAME` is a real future
  need, named in `design.md` D6 and left for a change that actually needs it.
- **Not profile discovery, a default-port-per-profile, or a rename/delete-profile command.** D6
  ships `--profile <name>` on `agentweave`/`status`/`stop` and `reset --profile <name>` only. Listing
  every profile on the machine, remembering a profile's last-used port, and renaming or deleting a
  profile beyond `reset` are named open follow-ups in `design.md` D6, not silently included.
