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

**Testability, resolved (amendment A2, 2026-08-17):** Playwright cannot drive `pywebview`'s WebView2
window on Windows — there is no Playwright backend for it, and the only theoretical route
(`--remote-debugging-port` + CDP attach) is not exposed or supported by pywebview. This is accepted,
not solved, on the strength of a binding constraint this decision now states explicitly rather than
argues informally: the native-window shell (`_open_app_window_native`, task 3.2) SHALL contain no
logic beyond `webview.create_window`/`webview.start`, the fallback's exception catch (including the
single diagnostic message it prints naming what's missing, per task 3.2 — that print is part of the
permitted catch, not extra logic), and the URL/title arguments `_hub_resolve_launch_url` already
resolves — no conditional rendering, no data fetching, nothing window-specific a bug could hide that
the identical URL served to a real browser would not also exhibit. Enforced by task 3.5 (a
diff-review/line-count check against `_open_app_window_native`'s body, not a runtime assertion —
there is nothing to execute against a window Playwright cannot open). Everything downstream of "a window pointed at this URL" — every page, every
interaction — is already exercised by the existing Playwright suite against the identical
FastAPI-served bundle in a real browser. That is a stronger claim than "we didn't test it" and a
weaker one than "the shell is proven," and this design states the difference rather than implying
full coverage either way. If the shell ever grows logic beyond window lifecycle — a custom menu, a
native file dialog, IPC — that logic becomes untested by construction and this testability claim no
longer holds; a future change adding any of those must re-open this question rather than assume it is
still covered.

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

## D6 — Named profiles: `--profile` selects a database, PID file and (optionally) a port together

**Decision (resolves amendment A3, 2026-08-17):** add a `--profile <name>` flag, default `"default"`,
to `agentweave` and `agentweave status`/`agentweave stop`. A profile resolves the three things that
are singletons today into one named identity:

- **Database.** The default profile keeps exactly today's corrected path
  (`Path.home() / ".agentweave" / "hub" / "data" / "agentweave.db"`, D1) — no migration, no existing
  install moves. A named profile resolves to
  `Path.home() / ".agentweave" / "hub" / "profiles" / <name> / "agentweave.db"`, created on first use.
  Profiles live *beside* `data/`, sibling under `HUB_DIR`, not inside it — so a profile-naive caller
  (direct `uvicorn`, no `--profile` reaching it) is unaffected and D1's default is untouched.
- **PID file.** `_hub_pid_file(port)` is already per-port (`cli.py:431`, the already-shipped minimal
  fix). This decision namespaces it per-profile too: the default profile is unchanged
  (`hub.pid` / `hub-<port>.pid`); a named profile is `hub-<profile>-<port>.pid` unconditionally, even
  at the default port, so the filename alone identifies which profile it belongs to and it can never
  collide with the default profile's file at the same port.
- **Port.** Unaffected for the default profile. A named profile has no port of its own in this
  decision, and `--port` already defaults to `DEFAULT_HUB_PORT` (8000) on every subparser today
  (`cli.py:1076,1105,1109`) — silently reusing that default for a named profile would let it collide
  with the default profile's own instance at the TCP level, a bind conflict that profile-namespaced
  database and PID-file paths do nothing to prevent, because those namespace *identity*, not the
  socket. So: when `--profile` names anything other than `"default"`, `--port` becomes a required
  argument — the CLI SHALL exit with a clear error naming both flags rather than silently defaulting
  to 8000. **Caught in round-2 cold review (2026-08-17):** the amendment's original phrase "`--port`
  stays required" was aspirational, not enforced anywhere in round 1's D6 text or `tasks.md` — nothing
  upstream would have caught the omission, since `--port`'s existing `default=8000` means an operator
  who forgets it gets a value, not an error. Remembering a profile's last-used port so this
  requirement could be dropped is a real convenience but optional, and not what closes A3 (the
  ambiguity A3 named was collision and blast radius, not needing to retype `--port`).

**`DATABASE_URL` still wins, unchanged.** The already-shipped minimal fix made `DATABASE_URL` an
explicit override; `--profile` computes a *default* database path the same way the bare CLI does
today, it does not add a second source of truth on top of an explicit override. If both are given,
`DATABASE_URL` wins and the CLI prints which one took effect, so the two never silently disagree.

**`cmd_reset --profile <name>`.** Without `--profile`, `cmd_reset` targets only the default profile's
`data/` directory, exactly as today — it does not enumerate or sweep `profiles/`. With
`--profile <name>`, it targets only that profile's directory. There is no sweep-everything mode in
this decision (no `--profile all`); deleting every profile is done one at a time, deliberately,
matching `CLAUDE.md`'s guidance against destructive shortcuts. This is what closes A3's stated
consequence: "with any additional instance, reset's blast radius is ambiguous" — after D6, `reset`'s
blast radius is always exactly one profile, named or default, never inferred.

**Docker is out of scope for this decision.** `docker compose up` has no CLI flag to carry a profile
through, and D2's `name: agentweave` pin already gives Docker one fixed instance — a profile-equivalent
for Docker (e.g. a per-profile `COMPOSE_PROJECT_NAME`) is a real future need but a separate one; the
exploration and A3 both raised only the CLI-side gap.

**Why a flag, not a config file.** Every other instance-selecting input this CLI already has
(`--port`, `--docker`/`--local`, `--no-detach`) is a flag decided at invocation, not a persisted
preference; `--profile` is the same shape of choice — "which instance am I talking to right now" —
made the same way.

**What this decision deliberately does not do**, named so a future round does not have to rediscover
them rather than silently included or silently dropped: a profile does not get its own remembered
default port; there is no `agentweave profile list` / discovery surface; there is no rename or
delete-profile subcommand beyond `reset --profile <name>`; `agentweave status` with no `--profile`
argument shows only the default profile, not every profile on the machine. Each is a real UX question
an operator should decide awake, not one this spec-only round should default through.

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

---

# Amendments resolved — 2026-08-17, round 1 (authored)

All three amendments above are resolved in this revision. Recorded here so the next round reviews a
stated resolution rather than re-deriving one from the objections alone.

- **A1 — resolved, verify-only, no change needed.** Re-checked live: `tests/test_cli.py` exists (not
  created by this change), currently holds four test classes —`TestTransportJsonAtomicWrite`,
  `TestSubprocessRunHasTimeout`, `TestTwoInstancesDoNotCollide`, `TestDownloadWithSha256` — confirming
  the already-shipped minimal fix (`c330431`) landed with its own test. `tasks.md` section 4 already
  carries the 2026-08-16 correction acknowledging the file exists and instructing extension, not
  creation; no further edit was needed there. This amendment was closed before this session, this
  entry only confirms it stayed closed.
- **A2 — resolved by a binding thin-shell constraint, not a process change.** D3 above now states
  explicitly that `_open_app_window_native` SHALL carry no logic beyond window lifecycle and the
  existing fallback — the informal argument the three review rounds never made explicit is now a
  requirement task (3.5) can check. Playwright still cannot drive the WebView2 window itself; that
  limitation is accepted and named, not solved, and the design says so rather than implying coverage
  it doesn't have.
  **Sharpened in round-2 cold review (2026-08-17):** the allowed list now explicitly names the
  diagnostic print on a caught exception (task 3.2's "a message is printed naming what's missing") as
  part of the permitted "fallback's exception catch," closing a reading under which task 3.5's
  reviewer would have to guess whether that print counts as extra logic.
- **A3 — resolved with D6 (named profiles), added above.** `--profile <name>` on `agentweave`/
  `status`/`stop`, a profile-namespaced database path and PID file, and `reset --profile <name>`
  scoping reset's blast radius to one profile. Docker's profile-equivalent is named and explicitly
  deferred, not silently dropped. `proposal.md`, the `app-lifecycle` spec delta, and `tasks.md` are
  updated in this same revision to carry D6 through to implementable tasks and a testable
  requirement — this was not left as a design-only decision the way A2's mitigation could be.

**Scope change this revision makes to the change as a whole:** D6 adds new CLI surface (`--profile`)
and a new spec requirement; it is not purely editorial. The round-3 gate that originally shipped this
change did not evaluate D6, because D6 did not exist yet. The spec-round protocol's cap is 3 with
approve-and-execute at cap for the *original* proposal; this revision restarts that count at round 1
for the amended scope, per the operator's own framing of these amendments as needing "a further review
round" before implementation begins — not a continuation of the original count.

---

# Round 2 — cold review, 2026-08-17

A fresh read (not a continuation of round 1's own authoring context) of `design.md`, `proposal.md`,
the `app-lifecycle` spec delta, and `tasks.md` as they stood after round 1, checking the four
questions the round-1 `next_action` posed.

**(1) Does D6 close A3's three named consequences?** Database and PID-file namespacing and
`reset --profile` scoping all check out against A3's table — verified by re-reading, not re-deriving.
But cold review surfaced a **fourth** consequence D6 itself introduces and A3's original table never
named, because A3 predates D6: a named profile with no explicit `--port` would silently resolve to
`DEFAULT_HUB_PORT` (8000, confirmed live at `cli.py:1076,1105,1109` — every subparser defaults it),
the same port the default profile normally runs on. Profile-namespaced database and PID-file paths do
not prevent this — they namespace *identity*, not the TCP socket — so two profiles started without
distinct `--port` values would collide at bind time, or worse, whichever started first would silently
"win" the port while the second's process failed in a way neither the database path nor the PID
filename would explain. **Fixed this round**, not deferred: D6's "Port" bullet above now makes
`--port` a required argument whenever `--profile` is not `"default"`, with the CLI erroring out by
name rather than defaulting into a collision. New tasks 1.8 (implementation) and 2.9 (regression test)
added to `tasks.md`; spec delta gets a new scenario. This is exactly the kind of gap the round-2
charter asked for — "not just gesture at" the consequences — the original three were closed cleanly,
the gap was in a fourth D6 introduced itself.

**(2) Is the A2 thin-shell constraint concrete enough for task 3.5 to be checkable?** Mostly, with one
looseness closed this round: D3's allowed list ("no logic beyond `webview.create_window`/
`webview.start`, the fallback's exception catch, ...") did not say whether the diagnostic message task
3.2 requires printing on a caught exception counted as part of "the exception catch" or as forbidden
extra logic — a reviewer checking 3.5 would have had to guess. Closed by naming the print explicitly
as part of the permitted catch, in both D3 and the amendments-resolved note above.

**(3) Do the seven new tasks (now nine, after this round's 1.8/2.9) cover D6 end to end — flag
parsing, path resolution, PID namespacing, reset scoping, `DATABASE_URL` precedence — without a gap?**
Yes, re-checked task by task against that five-item list: 1.4 (flag + path resolution +
`DATABASE_URL` precedence), 1.5 (PID namespacing), 1.6 (reset scoping), 2.5-2.8 mirror each
implementation task with a test, 2.9 now covers the port-collision gap found in (1). No further gap
found.

**(4) Is anything now inconsistent across the four edited files?** Checked task-to-scenario references
(2.5 against `TestTwoInstancesDoNotCollide`, 6.6 against the spec's "Two profiles do not collide" and
"Reset targets exactly one profile" scenarios, section 7 step 4 against the same) — all consistent.
No stale cross-reference found.

**Verdict: APPROVE**, with the port-requirement gap fixed in this same round rather than deferred to a
round 3 — small enough to close immediately per `next_action`'s instruction. This change is
3-round-eligible again for a future iteration's implementation pass. Implementation remains gated on
`pywebview` authorization per `STATE.json`'s `limits`; approval alone does not trigger `at_cap`'s
execute clause here, because that gate is about the spec-round count, not about dependency
authorization, and the two are independent.

**Verified, not trusted:** `npx openspec validate --changes --strict` after this round's edits — see
the log entry for the actual result.
