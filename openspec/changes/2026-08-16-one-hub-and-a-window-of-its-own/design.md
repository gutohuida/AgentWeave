# Design — One Hub, wherever it's launched from — and a window of its own

## Context

Two independently-installable distributions share this problem: `agentweave-ai` (the CLI,
`dependencies = []`) and `agentweave-hub` (the backend, real dependencies, `requires-python
>=3.11`). `src/agentweave/cli.py` imports `hub.main` lazily via `importlib.util.find_spec` — it never
imports `hub.config` directly, and nothing in `hub/hub/` imports anything from `src/agentweave/`.
There is no dependency edge either package could add to import the other's constants without also
adding a hard dependency where today there is an optional/lazy one. That constraint shapes D1.

## D1 — `config.py`'s default is corrected by independent computation, not by importing `cli.py`'s constant

**Decision:** `hub/hub/config.py`'s `database_url` default becomes
`f"sqlite+aiosqlite:///{(Path.home() / '.agentweave' / 'hub' / 'data' / 'agentweave.db').as_posix()}"`,
computed inline in `config.py` itself.

**Why not import `HUB_DIR` from `cli.py`:** `agentweave-hub` has no dependency on `agentweave-ai` in
either `pyproject.toml`, and the CLI currently imports `hub.main` only after it has already set
`DATABASE_URL` in the environment — the reverse import (`hub` importing from `agentweave`) does not
exist today and would be a new coupling between two packages designed to be installed and versioned
independently (`agentweave-hub` can run standalone, e.g. under Docker, with no CLI package present at
all). Duplicating the four-path-segment computation in both places is a small, explicit cost; a
cross-package import for four path segments is the larger one. If the two constants drift, a test
(`tasks.md`) asserts they compute the same value on the same interpreter.

**Effect on native mode:** none — `_hub_native_start` already sets `DATABASE_URL` in `os.environ`
before `hub.main` is imported, so this default is never consulted there. It exists for the two
callers that skip the CLI: direct `uvicorn hub.main:app`, and any future embedder.

**Effect on Docker mode:** none — `hub/docker-compose.yml`'s `environment:` block already sets
`DATABASE_URL=sqlite+aiosqlite:///data/agentweave.db` explicitly (a container-relative path, correct
because the Dockerfile's `WORKDIR` fixes it), which takes precedence over `config.py`'s Python-level
default regardless of what that default is. D1 does not touch Docker's `DATABASE_URL` value — only
D2's volume-naming fix applies there.

## D2 — Docker Compose gets a pinned project name

**Decision:** add a top-level `name: agentweave` to `hub/docker-compose.yml`. Compose's project name
prefixes every resource it creates, including the `hub-data` named volume; pinning it makes `docker
compose up` produce the same volume regardless of which directory it was run from, matching what
native mode has done since `ab53cf4`.

**Why not `COMPOSE_PROJECT_NAME` in `.env` instead:** that only takes effect for whoever's `.env` sets
it; a fresh clone or a different working `.env` reintroduces the directory-dependent default. A
`name:` key in the compose file itself is the one fix that applies unconditionally to anyone running
this file, which is the same reasoning D1 uses for fixing the default in `config.py` rather than
requiring every caller to set `DATABASE_URL`.

**Existing installs:** anyone who has already run `docker compose up` from a specific directory has a
volume named `<dirname>_hub-data`. Pinning the name going forward does **not** rename that existing
volume — it changes what a *future* `docker compose up` creates. This is the Docker half of D4's
migration question, addressed there rather than duplicated here.

## D3 — The desktop window: pywebview owns the calling thread when installed, with an unchanged fallback

**Decision:** when `pywebview` is importable, app mode calls `webview.create_window(...)` then
`webview.start()`, pointed at the same URL `_open_app_window` resolves today
(`_hub_resolve_launch_url`). When `pywebview` is not installed, behavior is **byte-identical** to
today — `_open_app_window`'s chromeless-browser-or-`webbrowser.open` path, unchanged. This keeps the
CLI's zero-runtime-dependency stance genuinely optional rather than aspirational: nothing breaks, and
nothing silently degrades in a way the operator can't see, if `pywebview` is absent.

App mode is not a flag a caller opts into: `main()` forces `parsed_args.app = True` for bare
invocation (`cli.py:1126`), which `create_parser()` states is "the only way to launch the app"
(`cli.py:1028-1029`), and `cmd_hub_start` forwards that same `app=True` down its Docker branch
(`--docker`/`--local`) exactly as it does down the native branch — there is no CLI surface today
that starts the Hub with `app=False`. So the decision below applies to every bare `agentweave`
invocation and every `agentweave --docker`/`agentweave --local` invocation, not to an opt-in flag.
Historical note: earlier commits (before `ab53cf4`, `2026-08-03-single-runtime`) had a real `--app`
flag on a `hub start` subcommand; this document keeps calling the concept "app mode" to avoid
implying that flag still exists.

**Why this is a real process-model change, not a drop-in:** `webview.start()` blocks the thread that
calls it until the window closes — this is inherent to how OS webview event loops work, not a
pywebview limitation to work around. Today's `detach` path spawns the Hub as a detached background
process and then fires `_open_app_window` as a non-blocking `subprocess.Popen`, so bare `agentweave`
(app mode forced on, default detach) returns immediately with the Hub still running. A pywebview
window cannot be opened that way without pywebview managing its own subprocess and IPC — out of scope
for this change.

**Resolution:** the Hub backend keeps starting exactly as it does today — detached (default) or
foreground (`--no-detach`), unchanged by this proposal. For the **detached** (default) path, app
mode's window becomes a **separate, additional blocking phase**: after the Hub is confirmed healthy
(the same `_hub_health_check` call already used), the CLI process blocks in `webview.start()` until
the operator closes the window, then exits 0. This mirrors what every real desktop app already does —
the process the user thinks of as "the app" is the one that exists for as long as its window is
open — and it composes cleanly with `detach`'s existing meaning ("the *Hub process* survives the
window closing," which stays true: only the window-owning CLI invocation exits, the detached uvicorn
process backing it keeps running, exactly as closing a browser tab today does not stop the Hub). The
**foreground** (`--no-detach`) path does not get this blocking phase at all — see the named exception
below, which explains why pywebview's own main-thread requirement rules it out for that path
specifically.

**Every default-detach launch, not just scripted or opt-in ones:** since app mode is forced on for
bare invocation and for the Docker branch (there is no `app=False` CLI surface — see above), a caller
that runs plain `agentweave` (or `agentweave --docker`) with default detach — which is every operator
who has not passed `--no-detach` — now blocks until the window closes, where it previously returned
in seconds. This is not a corner case for scripts that pass an extra flag; it is what happens by
default the next time anyone runs the CLI's one entry point. This is named in `proposal.md`'s Impact
section as a real behavior change, not hidden; `tasks.md`'s human-only section asks the operator to
confirm this is the experience wanted before it ships, since "the CLI command that starts your app now
waits for you to close the window" is a genuine UX judgment, not something a test can validate as
correct or wrong on its own. A caller that genuinely needs the old non-blocking start-and-return
behavior (e.g. this run's own driver, which starts the Hub via direct `uvicorn` rather than the CLI)
is unaffected — it does not go through `cmd_hub_start` at all.

**Window chrome:** a single window, no browser tabs/address bar/bookmarks (pywebview's default), title
"AgentWeave", pointed at `_hub_resolve_launch_url(port, cwd)` — the same URL resolution already used
for the browser fallback, so which project opens is unaffected by this change.

**Named exception: the `--no-detach` foreground path keeps the browser fallback unconditionally, and
is not wired through the native-window path at all.** `_wait_and_open_app` (`cli.py:654-661`) exists
specifically to run `_open_app_window` off the main thread — its own docstring says so ("Runs off the
main thread so a foreground (`--no-detach`) start can block on uvicorn while still opening the
browser") — because `--no-detach`'s main thread is already committed to blocking in `uvicorn.run()`
until Ctrl+C (`cli.py:798-802`). `pywebview` requires `webview.start()` to be called from the main
thread — confirmed via web research against pywebview's own issue tracker and FAQ (r0x0r/pywebview
issue #1251, "Why must pywebview be run on a main thread?"; pywebview's own FAQ), not assumed: Cocoa
enforces this strictly, and the library's documented pattern for a blocking backend task is the
*inverse* of a worker-thread call — hand the backend work to `webview.start(func, *args)` so
pywebview's own thread management starts it, rather than starting pywebview from inside an
already-spawned worker thread. Calling `webview.start()` from `_wait_and_open_app`'s worker thread
would not reliably work regardless of that thread question, because this call site's actual process
lifetime is governed by `uvicorn.run()` on the main thread returning on Ctrl+C — not by the window
closing, which is what this requirement's exit contract (above) describes for the other four sites.

Inverting the threading model instead — giving `webview.start()` the main thread and moving
`uvicorn.run()`'s foreground server to a worker thread, matching pywebview's documented pattern — was
considered and rejected here. `--no-detach` exists so a developer (or this run's own driver, which
starts the Hub this exact way) gets uvicorn's log output attached to the invoking terminal and Ctrl+C
as the stop mechanism; that is already a different exit contract from the other four call sites
("closes when its window closes" vs. "stops when its terminal is interrupted"), and manufacturing a
second, window-driven exit contract for the same invocation would make `--no-detach` behave
inconsistently with itself depending on whether `pywebview` happens to be installed, which is a worse
outcome than one call site staying on the existing fallback. So: `_wait_and_open_app` keeps calling
`_open_app_window` (today's non-blocking browser-window-or-tab behavior) exactly as it does now,
**regardless of whether `pywebview` is installed.** This is a real, narrow exception to "applies
uniformly to every launch path... neither is exempt" above — that sentence was about the native/Docker
split (both reach app mode through a path whose exit contract is "closes when the window closes"), not
about detached vs. foreground process mode, and is clarified in the spec delta to say so explicitly.

## D4 — Migration for existing data

Two populations, named in the exploration and resolved here rather than left open:

1. **Native-mode users** (bare `agentweave`, any flags, no direct `uvicorn`/Docker use). Already
   at `~/.agentweave/hub/data/agentweave.db`. **No migration — nothing changes for them.** D1/D2 do
   not touch this path.
2. **Direct-`uvicorn`/Docker-dev users** whose data sits at a project-relative `hub/data/agentweave.db`
   (native fallback, pre-D1) or inside a directory-prefixed Docker volume (pre-D2).

**Decision for population 2: leave existing data where it is; do not auto-migrate.** A silent
first-run migration that moves or copies a database file is exactly the kind of surprising, hard-to-
reverse action `CLAUDE.md`'s executing-actions-with-care guidance warns against, and this population
is by definition people running the Hub outside its one supported entry point (`app-lifecycle`'s
"Bare invocation is the only entry point" requirement already declares bare `agentweave` the only
supported way to begin) — most concretely, this run's own driver and any other Hub contributor
mid-development,
not an end operator who would be surprised to lose data. `tasks.md`'s test only needs to prove D1/D2
apply the corrected default going forward; it does not write a migration tool. Anyone in population 2
who wants their existing data at the new global path can copy the file themselves — a one-line
operation, not a feature. This is recorded as a deliberate choice, not an oversight: "detect and
migrate" was the alternative named in the exploration and rejected here because the population it
would protect is not the operator-facing population this bug report was about.

## D5 — pywebview's platform dependencies are documented, not solved

**Decision:** `pywebview` is added to `pyproject.toml`'s `[project.optional-dependencies]` as `app =
["pywebview>=5.0"]`. Its platform requirements — WebView2 runtime on Windows (ships with current
Windows 10/11 but is not guaranteed present on an unpatched install), WebKitGTK or Qt on Linux
(pywebview does not vendor either; the operator's distribution must have one), Cocoa/WebKit on macOS
(built in, no action) — are stated in the CLI's install documentation and in app mode's own failure
path: if `pywebview.create_window` raises because no webview backend is available, the CLI catches it,
prints what is missing, and falls back to `_open_app_window`'s existing browser behavior rather than
crashing the invocation (bare `agentweave` or `agentweave --docker`/`--local`). This keeps app mode
best-effort rather than a hard requirement, consistent with D3's "nothing breaks if pywebview or its
backend is unavailable."

**Explicitly not solved here:** vendoring or auto-installing a Linux webview backend. Out of scope,
named as an open cost in `proposal.md`'s Non-Goals, consistent with the exploration's Section 5.

## Naming and scope of the affected spec

This change extends the `app-lifecycle` capability (`openspec/specs/app-lifecycle/spec.md`), whose
purpose statement already is "the single supported way to begin and manage a local AgentWeave
instance." The existing "Bare invocation is the only entry point" requirement already established
"the one local AgentWeave runtime" as a concept; this change makes good on that phrase for the two
launch paths that did not yet honor it, and adds the desktop-window behavior as a new requirement
under the same capability rather than inventing a second one — starting the app and how its window
presents are two facets of the same "begin and manage a local instance" purpose.

---

# Amendments — 2026-08-16, before implementation

Three objections were raised against this change *after* it shipped at the round-3 gate and
*before* any of its 21 tasks were started. They are recorded here rather than in a new change
because all three concern the instance model this document already owns. A further review round
should resolve them before implementation begins.

## A1 — `tasks.md` section 4 is factually wrong about `tests/test_cli.py`

Section 4 states **in bold** that `tests/test_cli.py` does not exist and instructs creating it
"from scratch." **It does exist** — added in `b3f4b11`, last touched in `db01f40` (2026-08-10),
and since extended again. A literal reading of that instruction destroys existing coverage.

This was already recorded as the round-3 gate's non-blocking objection; it is repeated here
because it is the one amendment that causes data loss if implemented as written. Section 4 must
be reworded to *extend* that file.

## A2 — pywebview forfeits the app window's testability, and nothing weighed that

D3 chooses pywebview, which on Windows renders in WebView2. **Playwright cannot drive it.** There
is no Playwright backend for WebView2; the only route would be starting it with
`--remote-debugging-port` and attaching over CDP, which pywebview does not expose and does not
support.

What the change gives up is not hypothetical. Today's `_open_app_window` (`cli.py:634`) launches
Chrome or Edge with `--app=<url>` — a chromeless window that **is** Chromium, and which Playwright
drives for free. `scripts/uishot.py` already exists to do exactly that. So the app window is
automatable today and would stop being automatable after D3.

This is not necessarily a reason to reject pywebview. The mitigating fact is that app and web are
not two builds: one FastAPI process serves one bundle, and the window is a window onto the same
`http://127.0.0.1:PORT`. Anything Playwright asserts through a browser holds for the app window
too. But that argument only works if the *shell* stays thin — window lifecycle, the main-thread
rule, and the absent-backend fallback are then the only untested surface, and D3 must say so and
keep them minimal. The three review rounds never made this trade explicitly.

## A3 — the instance model needs a named profile, not just a moved default

This change's thesis is that a database derived from the launch directory is wrong. That is right,
but the fix as written leaves the opposite problem: **exactly one instance is reachable**, and
`--port` is a trap that looks like it produces a second one.

Three singletons made it so, all in `cli.py`:

| Singleton | Consequence |
|---|---|
| `_hub_native_start` overwrote `DATABASE_URL` unconditionally | a second start opened the *same* SQLite file — two writers, one project list |
| `_hub_pid_file()` returned one `hub.pid`, not per-port | the second start erased the first's record; `stop` and `status` went blind to it |
| `cmd_reset` deletes `HUB_DIR/data` wholesale | with any additional instance, reset's blast radius is ambiguous |

A fourth sat in the UI: `hub/ui/vite.config.ts` pinned its dev proxy to `http://localhost:8000`,
so `npm run dev` could only ever reach the default instance.

The first two and the fourth are **already fixed** as a minimal unblocking change, ahead of this
one: `DATABASE_URL` is now honoured when set, `_hub_pid_file(port)` is per-port with
`DEFAULT_HUB_PORT` keeping the historic unsuffixed name, and the dev proxy reads `AW_DEV_HUB`.
Guarded by `TestTwoInstancesDoNotCollide` in `tests/test_cli.py`. That is deliberately the smallest
change that removes the trap; it does **not** introduce a profile concept, and `cmd_reset` is
untouched.

**What this change should then own** is the named concept those fixes leave implicit:

```
agentweave                              # default profile, app window
agentweave --profile dev --port 8010    # its own database, its own PID file, browser
```

A profile carries the database, the PID file and the default port together. The default profile
keeps today's exact path, so no existing install migrates. Profiles live *beside* `data/`, not
inside it, so `reset` cannot sweep them all, and `reset --profile <name>` targets one.

**Why this belongs here and not in a separate change:** profiles do not contradict D1, they
complete it. D1's enemy is the *accidental* database, derived from wherever you happened to
launch. A profile is a *named, deliberate* one. Two changes both editing the instance model would
have to agree about which owns `DATABASE_URL`, the PID file and `reset`; one change does not.

**Cost if this is deferred instead:** the minimal fix above already makes two instances work via
`DATABASE_URL` and `--port`, so nothing is blocked — but the operator carries the paths by hand,
and `reset`'s blast radius stays ambiguous with a second instance present.
