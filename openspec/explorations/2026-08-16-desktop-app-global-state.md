# Exploration — A real desktop app with one global state (2026-08-16)

**Status:** Research and comparison, not a decision. Written for queue item `Q6-desktop-and-global`
in `.claude/autonomous/STATE.json`, at the operator's request: *"I also want a full app experience
with agentweave no more opening on the browser"* and *"agentweave should be global... if I ran
agentweave from different folders it creates a different agentweave which is weird. Now that I want
it to be a full app opening always restore the same state."*

Per the queue item's own instruction this is an exploration, not a proposal: no toolchain beyond pip
was installed (pre-authorised default, recorded in `decisions_for_user`), and nothing here is
implemented. Written to be read cold, against `review_criteria` on the queue item: does it compare
alternatives with evidence, specify global state per-OS with a migration path, say what happens to
an existing `data/agentweave.db`, and state the desktop shell's rejected alternatives and why.

---

## 1. Re-diagnosing "different folder, different AgentWeave" — it is two bugs, not one, and one is already half-fixed

The queue item's `detail` field, written at prep time, names a single root cause:
`hub/hub/config.py:9`'s `database_url: str = "sqlite+aiosqlite:///data/agentweave.db"` is a relative
path resolved against the Hub process's working directory. That line is still exactly as described
— confirmed again in Entry 22 and again here. But reading the code that actually calls it shows the
picture is more specific, and the fix is narrower than "make the config default absolute."

**Native mode (`agentweave hub-start`, no `--docker`) already writes to a global, per-user path, not
a per-folder one.** `_hub_native_start` (`src/agentweave/cli.py:664`) never lets `config.py`'s
relative default take effect: before it imports `hub.main` at all, it computes
`db_path = HUB_DIR / "data" / "agentweave.db"` and sets `os.environ["DATABASE_URL"]` to that
absolute path (`cli.py:700-710`), and `HUB_DIR = Path.home() / ".agentweave" / "hub"`
(`cli.py:211`) — fixed regardless of the caller's `cwd`. `git log` dates this to commit `ab53cf4`,
"local multi-project workspace phase 2: CLI lifecycle and legacy binding" (2026-08-03). So the
CLI-driven path the product actually ships — the one a `pip install agentweave-ai` user runs — has
not had this bug since the 3rd. The relative default in `config.py` only fires when something
imports `hub.main` without going through `_hub_native_start` first, which happens in exactly two
places:

1. **Anyone who runs `uvicorn hub.main:app` directly**, e.g. from inside `hub/` with no `DATABASE_URL`
   set. This is not a hypothetical — it is this driver's own `restart_command` in this very
   `STATE.json` (`cd hub && python -m uvicorn hub.main:app`), and it is exactly the pattern a Hub
   contributor uses while developing. It resolves against whatever directory the shell happened to
   `cd` into.
2. **Docker mode** (`agentweave hub-start --docker` or `--local`, and `hub/docker-compose.yml`
   directly). Here the *container's* relative path is fine — the Dockerfile's `WORKDIR` fixes it —
   but the **named volume that backs it is not**. `hub/docker-compose.yml` declares a bare
   `hub-data:` volume with no top-level `name:` key (confirmed by grep: no `^name:` anywhere in the
   file). Docker Compose derives the *project name* — the prefix on every resource it creates,
   including named volumes — from the containing directory's basename unless `COMPOSE_PROJECT_NAME`
   or a `name:` field overrides it. Run `docker compose up` from `~/AgentWeave/hub` and from a
   clone at `~/work/AgentWeave/hub` and Compose creates two differently-prefixed volumes
   (`hub_hub-data` vs. `agentweave_hub-data`), i.e. two databases, for what the operator experiences
   as the same app.

So: **the operator's observed symptom is real, but it is not (or is no longer) the native CLI path.**
It is the direct-uvicorn dev path and the Docker Compose path. This matters for scoping the fix —
"pin `config.py`'s default to an absolute, home-relative path" closes both remaining holes at the
source (belt-and-braces under native mode, which already overrides it; a real fix for anyone who
imports `hub.main` without going through the CLI) and "give the compose file an explicit `name:`"
closes the Docker one. Neither requires a desktop shell decision to happen — they are corrections to
today's architecture, independent of Section 3's shell choice, and should probably be filed and
fixed on their own rather than waiting on Q6's full spec round. Recorded here rather than fixed now
because Q6 is scoped as research-first per its own `detail` field.

**What "global state" should mean, then, restated precisely:** not just the database file, but
everything the Hub treats as instance-level rather than project-level state — the bootstrap API key,
the `.env` it scaffolds, the SSE ticket secret, logs. `_hub_native_scaffold` already writes `.env`
beside the same `HUB_DIR / "data"` it derived the db path from, so this is already consistent within
native mode; it is the same two gaps (direct uvicorn, Docker) that need closing, not a new design.

## 2. What "global" does NOT mean — the multi-project architecture is already correct and must not move

`CLAUDE.md`'s "Local multi-project boundary" section is explicit: *"One local Hub instance owns a
collection of projects. A project's database ID is durable and its canonical working directory is a
unique binding recorded by a non-secret `.agentweave/project.json` marker."* `cli.py:828` registers
`Path.cwd()` as a project on `hub-start` — per-folder *project registration* is correct and
intentional; it is only the *Hub's own instance state* (one database, one set of credentials, one
running process) that should be single and global. A reader of this document should not walk away
thinking "make everything global" — only the Hub's own home, not the projects it tracks.

## 3. Desktop shell options

Three real candidates, researched 2026-08-16 (web search; AgentWeave already ships a FastAPI
backend serving a built static React bundle from `hub/hub/static/ui`, so "wrap an existing local web
app" is the shape of the problem in all three cases, not "port to a native toolkit").

### Electron

Bundles a full Chromium + Node.js runtime with every app. Mature ecosystem, but heavy: reported
**200-400MB RAM at startup**, app sizes **exceeding 100MB**, and **1-2s cold start** on mid-range
hardware
([tech-insider.org](https://tech-insider.org/tauri-vs-electron-2026/)). Requires a Node.js/npm
toolchain to build the shell itself (the Hub UI already needs Node for its Vite build, but the shell
would be a second, separate Node project with its own packaging pipeline — `electron-builder` or
`electron-forge` — not a reuse of the existing `hub/ui` build). **Rejected**: heaviest of the three
on every axis that matters here (install size, RAM, and the zero-runtime-dependency ethos
`pyproject.toml` states for the CLI), and it does not reduce the toolchain surface — it adds a
second Node pipeline alongside the one that already exists for `hub/ui`.

### Tauri (and PyTauri)

Uses the OS's *existing* webview — WebView2 (Chromium-based) on Windows, WKWebView on macOS,
WebKitGTK on Linux — instead of bundling a browser. Reported **96% smaller** than the equivalent
Electron app, **20-40MB RAM**, **under 10MB** app size, **under 0.5s** startup
([tech-insider.org](https://tech-insider.org/tauri-vs-electron-2026/)). A binding named **PyTauri**
now exists specifically to let a Python backend drive a Tauri shell
([BigGo News](https://biggo.com/news/202510140726_PyTauri_Python_Tauri_Binding)), which is the
closest fit to AgentWeave's actual architecture (Python backend, web frontend) among the two "real"
desktop toolkits. But Tauri's shell itself is a Rust binary — building or customizing it requires a
Rust toolchain, which is exactly what this run's `limits` forbids installing this session ("No new
language toolchain may be installed this run (no Rust, no Node-for-Electron)"). **Not rejected on
merit — it is the best-specced option on every measured axis above — but excluded from this run's
recommendation by the standing constraint**, and recorded as the `decisions_for_user` cost of that
constraint: *"the desktop-app spec may recommend Tauri or Electron and stop one step short of a
working prototype."* If the operator lifts the no-Rust constraint, PyTauri is the strongest
long-term candidate and should be re-evaluated first.

### pywebview

A pure-Python package (`pip install pywebview`) — "a lightweight cross-platform wrapper around a
webview component... essentially Electron for Python minus huge executable sizes"
([search summary, citing pywebview's own docs](https://pywebview.flowrl.com/)). It does not bundle a
browser engine; it uses the OS's native webview: WebView2 on Windows (Chromium-based; the runtime
ships with Windows 11 and Windows 10's later updates but must be present, same dependency Tauri
carries on Windows), Qt or GTK+WebKitGTK on Linux (developer must pick one; both need system
packages — e.g. `python3-gi gir1.2-webkit2-4.0` on Ubuntu — pywebview does not vendor them), and
Cocoa/WebKit on macOS (built into the OS, no extra install)
([pywebview installation guide](https://pywebview.flowrl.com/guide/installation.html),
[GitHub issue #805](https://github.com/r0x0r/pywebview/issues/805)). Working examples already pair
it with a FastAPI backend and a Vite-built frontend in exactly AgentWeave's shape — backend serves
the API, pywebview opens a window pointed at it
([fastapi-desktop](https://github.com/zy7y/fastapi-desktop),
[Medium walkthrough](https://medium.com/@takahiro.zt899/creating-a-desktop-app-with-pywebview-vite-and-react-7785db86490f)).
**Selected for this run's recommendation**: the only one of the three that needs *no* new language
toolchain — it is `pip install`-able into the same interpreter the Hub already runs in, consistent
with the CLI's zero-runtime-dependency stance if shipped as an *optional* extra (`agentweave-ai[app]`
or similar) rather than a base dependency. Its cost is Linux packaging friction (GTK/Qt system
packages pywebview does not vendor) and that it does not solve installer/code-signing/auto-update on
its own — those stay open problems either way (see Section 5).

### Comparison table

| | Electron | Tauri / PyTauri | pywebview |
|---|---|---|---|
| Install size | >100MB | <10MB | ~0 (uses OS webview) |
| RAM at idle | 200-400MB | 20-40MB | comparable to Tauri (OS webview, no bundled engine) |
| Cold start | 1-2s | <0.5s | comparable to Tauri |
| New toolchain required | Node (separate from `hub/ui`'s) | **Rust** | none — pure `pip install` |
| Fits this run's no-new-toolchain limit | No | **No** | **Yes** |
| Python backend fit | indirect (IPC to Node main process) | via PyTauri binding (new, 2026) | direct — same interpreter |
| Windows dependency | bundled Chromium (none) | WebView2 runtime | WebView2 runtime (same) |
| Linux dependency | bundled Chromium (none) | WebKitGTK | WebKitGTK or Qt, developer's choice |
| macOS dependency | bundled Chromium (none) | WKWebView (built in) | Cocoa/WebKit (built in) |
| Code signing / auto-update | mature (electron-builder) | mature (tauri-bundler) | **not solved by the library itself** — see Section 5 |

Sources: [tech-insider.org Tauri vs Electron 2026](https://tech-insider.org/tauri-vs-electron-2026/),
[BigGo News on PyTauri](https://biggo.com/news/202510140726_PyTauri_Python_Tauri_Binding),
[pywebview docs](https://pywebview.flowrl.com/),
[pywebview installation guide](https://pywebview.flowrl.com/guide/installation.html),
[fastapi-desktop example](https://github.com/zy7y/fastapi-desktop).

### The option that is already half-built and costs nothing: app-mode browser window

Worth naming because it already exists in this codebase and was not mentioned in the queue item's
`detail`. `src/agentweave/cli.py:634`, `_open_app_window`, already opens the Hub's URL in a
**chromeless** window (`chrome --app=<url>` / `msedge --app=<url>`, falling back to
`webbrowser.open`) via the existing `--app` flag on `hub-start` (`cli.py:819-828`). This is not "the
browser" in the sense the operator means — no tabs, no address bar, no bookmarks bar — it is
functionally a webview window, just one borrowed from an installed Chrome/Edge instead of a
dedicated runtime. It requires zero new dependency and already ships. Its ceiling is real: no true
OS integration (dock/taskbar icon is the browser's, not AgentWeave's; no native menu bar; quitting
the browser process is indistinguishable from any other Chrome window in a task switcher; no
auto-launch-on-login without more plumbing). Recorded as a candidate *floor*, not a replacement for
Section 5's recommendation — but any spec proposal should explicitly say why pywebview is worth the
extra dependency over this already-shipped zero-cost option, rather than silently assuming a new
package is needed.

## 4. Global state: what already works, what does not, and the migration path

**Per-OS location, if `config.py`'s default is corrected to match what native mode already does:**
`Path.home() / ".agentweave" / "hub" / "data" / "agentweave.db"`. This resolves correctly today on
Windows (`Path.home()` → `C:\Users\<user>`), macOS, and Linux (`~`) — it does not need a new
dependency like `platformdirs` to get this right, and adding one would be worth flagging against the
CLI's `dependencies = []` stance in `pyproject.toml` if a future proposal reaches for it. `platformdirs`
would place data more idiomatically per OS (`%LOCALAPPDATA%` on Windows,
`~/Library/Application Support` on macOS, XDG on Linux —
[platformdirs docs](https://platformdirs.readthedocs.io/en/latest/explanation.html)) but that is a
refinement on top of an already-working global path, not a fix for the reported bug, and should be
weighed against the zero-dependency stance rather than assumed.

**Migration path for someone who already has a `data/agentweave.db`:** two populations exist and
need different handling, worth stating explicitly rather than discovering at implementation time:

- Someone who has only ever used `agentweave hub-start` (native, no flags) already has their data at
  `~/.agentweave/hub/data/agentweave.db` — no migration needed, nothing changes for them.
- Someone who ran `hub/docker-compose.yml` directly, or `uvicorn hub.main:app` from inside `hub/`,
  has a database at a project-relative `hub/data/agentweave.db` (native fallback) or inside a
  directory-prefixed Docker volume. A future proposal needs to decide: detect and offer to migrate
  that file into the global location on first run of a corrected build, or leave it and only apply
  the global default going forward (stale local data left orphaned, silently). Not decided here —
  flagged as exactly the kind of question `review_criteria` asks this exploration to surface, not
  resolve.

## 5. What this exploration deliberately leaves open

- **Code signing and auto-update** for any of the three shells is a real, unresearched cost — this
  pass covered runtime architecture, not distribution. A future proposal needs its own pass on this
  before committing to "ship a desktop build," since an unsigned app draws OS warnings on both
  Windows (SmartScreen) and macOS (Gatekeeper) that a `pip install` never faced.
- **Whether the Rust-toolchain constraint should be lifted** for PyTauri, given it beats pywebview on
  every measured resource axis. This is exactly the "if the spec concludes a toolchain is required,
  record that in `decisions_for_user`" case the queue item's `constraint` field anticipated —
  recorded here, not decided.
- **Packaging pywebview's Linux GTK/Qt dependency** so it does not become a new "well it works on my
  machine" gap for a project whose CLI currently declares zero runtime dependencies.
- This document does not touch `hub/docker-compose.yml`'s missing `name:` key or `config.py`'s
  relative default — both are small, mechanical, and independent of the shell decision. They are
  named in Section 1 as findings, not fixed here, because Q6 is scoped as research-first; a future
  iteration could fix them as a small, separate, low-risk change ahead of or alongside the spec
  round.

## 6. Recommendation for the coming spec round

1. **Desktop shell: pywebview**, as an optional extra, wrapping the existing FastAPI+static-bundle
   Hub with no new language toolchain — the only candidate compatible with this run's constraint,
   and honestly the best fit for a Python backend regardless of the constraint. Record Tauri/PyTauri
   as the rejected-for-now alternative with its evidence (Section 3), so a future session with the
   constraint lifted does not re-run this research.
2. **Global state: fix `config.py`'s default and `docker-compose.yml`'s missing `name:`**, both
   small and independent of the shell choice, so every launch path (native, direct uvicorn, Docker)
   agrees with what native mode has already done correctly since 2026-08-03.
3. **A migration decision** for the two populations in Section 4, made explicitly rather than
   defaulted.

None of this is implemented. The next step per the spec-round protocol in `STATE.json` is an
AUTHOR pass producing `openspec/changes/2026-08-16-<name>/` (proposal, design, tasks, spec deltas),
followed by an independent cold REVIEW pass against this document's own Section 6 and the queue
item's `review_criteria`.
