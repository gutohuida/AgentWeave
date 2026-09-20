# Proposal — a Hub that was not told which database refuses to open one

**Round 1, 2026-09-20 (day window).** Finding: **F388 (A)**. The remedy was decided on 2026-09-19
(`spec-queue/DIRECTION.md`, item 2): **(a) refuse the implicit default, (b) name the resolved path at
startup, (d) fix the docstring that calls the dangerous path the safe one.** *Rejected* were logging
alone (prevents nothing) and **(c)** the sentinel row, which needs a migration installed against the
very database being protected. **R1's job was to explore how to build (a), not whether.** R2 and R3
have not run.

## Why

On 2026-09-19 a day window started a throwaway Hub from `hub/` with `py -3.11 -m uvicorn
hub.main:app`. Its `DATABASE_URL` did not survive a `kill` + `rm` + restart sequence inside one Bash
tool call, the process fell back to `_default_database_url()`, and it attached to
`~/.agentweave/hub/data/agentweave.db` — **the operator's live `:8000` database, 348 runs and 12,500
event logs of real work.** The recovery (`taskkill /IM python.exe /T`) also killed the operator's own
app, which was down for roughly three hours. The cause is measured and is not re-derived here
(`scripts/drive/FINDINGS.md` § F388; `.claude/handoffs/DEAD-ENDS.md` § *Starting a Hub from source
can land on the operator's real database*).

Three things make the default dangerous rather than merely present:

- `hub/hub/config.py:23` — `database_url: str = Field(default_factory=_default_database_url)`. **A
  missing environment variable is indistinguishable from a deliberate choice of that path.**
- `hub/hub/config.py:12-15` — the docstring asserts the default is *"Only consulted by callers that
  skip the CLI (direct `uvicorn hub.main:app`, or any future embedder)"* and that *"this default
  never fires there"*. Direct `uvicorn hub.main:app` is **exactly what this repository's own
  `CLAUDE.md` instructs an agent to run** for the trial Hub. The comment describes the dangerous
  path as the safe one.
- Nothing downstream ever refuses a path. `init_db` creates the parent directory
  (`hub/hub/db/engine.py:346-350`) and SQLite creates the file, so **there is no path a typo can
  name that the Hub declines to open or create** (measured — `design.md` D11).

## What R1 found that the finding did not say

1. **F388 is spec'd behaviour, not an oversight.** `openspec/specs/app-lifecycle/spec.md:16-19`
   normatively requires that *"the one local AgentWeave runtime SHALL resolve to the same database
   and instance state regardless of which directory it was launched from, whether started through
   bare `agentweave` …, a direct `uvicorn hub.main:app` invocation, or `docker compose up`"*, and the
   scenario **"The Hub's own database is launch-directory-independent"** (`:46-53`) spells out a
   direct `uvicorn` *with no `DATABASE_URL` set* resolving to the home path. **(a) reverses a current
   requirement**, so this change carries a `MODIFIED` delta and not only a code edit. A round that
   treated (a) as a pure refactor would have shipped a change contradicting the corpus.
2. **The one line in the tree that already names the database has never been seen by anyone.**
   `hub/hub/db/engine.py:228` logs `logger.info("Alembic migrations applied to %s",
   settings.database_url)`. Measured: before `init_db` the root logger has no handler at all
   (`logging.lastResort`, WARNING-only), and after `init_db`'s `fileConfig` it has a console handler
   at **level `WARNING`**, because `hub/hub/alembic.ini:20-22` sets `[logger_root] level = WARN`.
   `logging.getLogger("hub.db.engine").isEnabledFor(logging.INFO)` is **`False`** in both states. So
   **(b) written as `logger.info` would be invisible**, which is F151's failure repeated: this repo's
   dominant mode is a fix that passes its tests and cannot fire in production.
3. **`.env` is a third source, and it is resolved against the working directory.**
   `SettingsConfigDict(env_file=".env")` (`config.py:21`) takes a *relative* name.
   `hub/.env` on this machine sets `DATABASE_URL=sqlite+aiosqlite:///data/agentweave.db` — itself a
   **relative** path, the exact bug `2026-08-16-one-hub-and-a-window-of-its-own` D1 removed from
   `config.py` and left standing in `hub/.env.example:5`. So "the variable is absent" is not one
   condition but three, and a refusal must be defined over all of them (D3).
4. **The blast radius includes `make ui`.** `scripts/refresh_ui_bundle.py:110` imports `hub.main`
   with no `DATABASE_URL` set. Probed by making the field required for real: `make ui` and
   `make ui-check` die with a raw `pydantic_core.ValidationError`. `agentweave --help` and
   `agentweave doctor` are **unaffected** (neither imports `hub`), Docker mode is unaffected
   (`hub/docker-compose.yml:34` sets the variable), and native `agentweave` is unaffected
   (`src/agentweave/cli.py:1028` sets it before importing `hub`). Group 3 covers the one caller that
   breaks.
5. **A required field alone produces a message that helps nobody.** Measured verbatim:
   `1 validation error for Settings / database_url / Field required [type=missing, input_value={},
   input_type=dict]`. It names neither the database it refused to open nor either way to set the
   variable, and it arrives as an import-time traceback before uvicorn prints a line. D2 chooses a
   **raising `default_factory`** instead, measured to propagate the exception unwrapped and to not
   run at all when any source supplied a value.
6. **`DEAD-ENDS.md`'s F388 practice contains one false sentence.** It says *"`sqlite3`/`aiosqlite`
   will not create a missing parent directory … making directory-existence the cheap thing to check
   first."* True of raw `aiosqlite` (measured: `OperationalError: unable to open database file`) and
   **false of the Hub**, which calls `os.makedirs(..., exist_ok=True)` first (`engine.py:346-350`).
   The diagnostic survives for a *stronger* reason and is corrected rather than dropped (D10).

## What changes

- **(a)** `config.py` stops defaulting `database_url`. When no source supplies one, `Settings()`
  raises a Hub-specific error naming the path it refused to open and both supported ways to say what
  to open. `_default_database_url()` survives as a function — it is what the message quotes and what
  the CLI-drift test compares against (D7).
- **(b)** The Hub names its database at `WARNING` **before anything opens it**, saying whether the
  file already existed and carrying this process's OS PID, so the recovery is killing that PID
  rather than a blanket `taskkill /IM python.exe /T`. It deliberately does **not** print a port,
  because `settings.aw_port` is not the port uvicorn was given (D5, D6, D9).
- **(d)** The docstring is rewritten to say what is true.
- The `app-lifecycle` requirement and its scenario are modified; `hub/.env.example`'s relative path is
  made absolute; `CLAUDE.md` and `.claude/reference/hubs.md` lose the guarantee they cannot keep and
  gain the mechanism that can.

## What this change does NOT do

**F388's severity A rests on the third loss — *the recovery is worse than the fault*.** (a) removes
the route that produced the 2026-09-19 incident and (b) makes any future attachment readable in one
line before the first write. **Neither gives a Hub that is already attached a safe way to detach**,
and this change does not add one; D9 states exactly what is left standing, what (b) does for it, and
why the remaining piece is not in `config.py`'s blast radius. It is named here rather than left for
the review page to notice.

## Impact

- **Code:** `hub/hub/config.py` (the refusal, the docstring), `hub/hub/main.py` (the startup line —
  D6 fixes which module).
- **Tests:** `hub/tests/test_config.py` — two tests in `TestDatabaseUrlDefault` /
  `TestDatabaseUrlDriftAgainstCli` fail under (a) as written (measured: `2 failed, 2 passed`) and are
  rewritten, not deleted.
- **Callers:** `scripts/refresh_ui_bundle.py` only.
- **Specs:** `app-lifecycle` — one `MODIFIED` requirement.
- **Prose:** `CLAUDE.md`, `.claude/reference/hubs.md`, `.claude/handoffs/DEAD-ENDS.md`,
  `hub/.env.example`.
- **No migration.** **No `hub/ui/src` change, so no bundle refresh and nothing reaches the operator's
  live `:8000` app on their next reload.**
