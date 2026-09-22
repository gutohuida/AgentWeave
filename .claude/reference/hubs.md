# The Hubs on this machine — trial `:8010` and the operator's `:8000`

Moved out of `CLAUDE.md` on 2026-09-15 so it is read when needed rather than paid for on every
request. The safety rules stay in `CLAUDE.md`; this file is the runbook behind them.

Confirm which database a running instance actually serves before trusting any doc, this one
included — these paths have moved before and will again, and `CLAUDE.md` has been wrong about them
for a day at a time. The cheap check: hit the API, then compare mtimes across the candidates.

## The trial Hub — rebuilt 2026-09-07 on a clean database

| | |
|---|---|
| **Port** | `8010` |
| **Database** | `~/.agentweave/hub/profiles/trial/agentweave.db` — created fresh 2026-09-07; at head `0102` (read from its `alembic_version`, 2026-09-12) |
| **PID file** | `~/.agentweave/hub/hub-trial-8010.pid` (per-launch-script; any other `hub-*.pid` may be stale — check `Get-Process -Id <pid>` before trusting one) |
| **This repo registered as** | `proj-d85a82bf4216`, working directory the repo root |
| **Bootstrap key** | `~/.agentweave/hub/profiles/trial/bootstrap-key.txt`, sent as `Authorization: Bearer <key>` (not `X-API-Key`) |

**Everything this section used to name was deleted on 2026-09-07**, at the operator's instruction,
to get a clean slate: the `beta`, `trial`, `dev` and `drive8011` profiles, their seven `.bak` files,
and `<repo>/hub/data/agentweave.db`. The old registration `proj-5e960453` went with them.

Start the trial Hub — **from `hub/`, not the repo root**, **from source, not the console script**:

```bash
cd hub
DATABASE_URL="sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/profiles/trial/agentweave.db"   py -3.11 -m uvicorn hub.main:app --port 8010 --host 127.0.0.1
```

Since `a-hub-that-was-not-told-which-database-refuses-to-open-one` (2026-09-22), a launch with no
`DATABASE_URL` reaching the process refuses to start rather than falling back to the operator's
default — so a broken launch here fails loudly, and the startup line (printed before anything
opens) names the absolute file it opened, whether it existed before, and its pid: read that line
rather than inferring the database from what is missing.

Point the Vite dev server at it with `AW_DEV_HUB=http://127.0.0.1:8010 npm run dev`, and
`scripts/uishot.py --url http://127.0.0.1:8010` for screenshots.

## The operator's real instance on `:8000`

It **runs this checkout, by intent** (operator, 2026-09-13), on the default profile, database
`~/.agentweave/hub/data/agentweave.db`. **Corrected 2026-09-22 (R4 review,
`a-hub-that-was-not-told-which-database-refuses-to-open-one`) — the prior sentence naming the
desktop shortcut's command line was false:** the desktop shortcut (`C:\Users\huida\Desktop\
AgentWeave.lnk`) targets `pythonw.exe -m agentweave`, cwd `C:\Users\huida`, which sets
`DATABASE_URL` (`cli.py:1038`) before spawning `[sys.executable, "-m", "uvicorn", "hub.main:app",
"--host", "127.0.0.1", "--port", "8000"]` with `env=os.environ.copy()`
(`cli.py:1066-1093`) — it is the CLI that runs uvicorn, not a direct `pythonw.exe -m uvicorn` line.
A measured live PID's command line matched that spawn but ran `python.exe`, not `pythonw.exe`,
meaning it came from a terminal `agentweave` run, not the shortcut — do not write that a specific
PID is the shortcut's spawn without checking its interpreter. Both routes go through the CLI, so
both are **told**: `DATABASE_URL` reaches the process and (a)'s refusal never fires here. It shares
no database with the trial Hub, but it shares this code, and consequences follow:

- It runs without `--reload`, so a Python change reaches it only when the operator restarts it.
- A restart runs this checkout's migrations **against the operator's real database**.
- It serves `hub/hub/static/ui` straight from this checkout, so **a committed UI bundle reaches the
  operator's live app on their next reload.** A broken bundle is a broken real app.
- The detached child's `stdout`/`stderr` are `DEVNULL` (`cli.py:1096-1097`), so group 2's startup
  line (the database it opened, existed-before, pid) is emitted here and **read by no one** — a
  known limit of that line, not a defect in it.

Never restart it, migrate it, or write to its database. Read-only (`mode=ro`) SQLite reads have
been fine. The PyPI install in `C:\Users\huida\agentweave-live` still exists, but it is not what
serves `:8000`; earlier revisions of `CLAUDE.md` said it was.

## Startup traps

**Do not use `agentweave --port 8010` here.** The console script is the *installed*
`agentweave-hub`, whose bundled migrations lag this checkout, so on any branch past the installed
head it dies with `Migration failed: Can't locate revision identified by '00NN'`. This cost two
sessions on 2026-08-24 before it was written down. The gap is large: the installed build is PyPI
**1.1.0** at migration head `0081`, while this checkout is at `0102`+ and well over 1,400 commits
past the `Release 1.1.0` commit — both still calling themselves `1.1.0`.

**`agentweave` cannot be started from this repo's root.** `_hub_native_start` spawns
`python -m uvicorn hub.main:app`, and `-m` puts the working directory on `sys.path[0]` — so this
repo's own `hub/` directory shadows the installed `hub` package and the child dies with
`ImportError: cannot import name '__version__' from 'hub' (unknown location)`. The parent process
is unaffected (console scripts do not put the cwd on the path), so migrations run and only the
spawned server fails, 60 seconds later, with its output already sent to `DEVNULL`. Starting from
`hub/` avoids the shadowing but makes the CLI register `<repo>/hub` as a second project — delete
that one if it appears. This only bites a repository that contains a top-level `hub/` directory,
which is to say: this one, the one being dogfooded.

`hub/data/agentweave.db` no longer exists — **deleted 2026-09-07** with the other stale databases.
It was the pre-migration original, created by a bare `uvicorn` launch from `hub/` landing on
`config.py`'s relative default. If a `hub/data/` directory reappears, a launch has fallen through
to that relative default instead of naming a profile: treat it as a symptom, not as a database to
preserve.
