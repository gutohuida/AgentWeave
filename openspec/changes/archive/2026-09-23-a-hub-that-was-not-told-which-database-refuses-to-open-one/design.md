# Design — a Hub that was not told which database refuses to open one

**Round 1, 2026-09-20.** Everything below was measured on this machine unless it is labelled
*unverified*. The measurement scripts were throwaway (`testbed/scratch/f388/`, deleted); what they
returned is transcribed here so R2 and R3 can re-derive rather than re-run.

**Round 2, 2026-09-20.** An independent re-derivation against the code, not a re-read of R1. Method:
every file opened before any part of this document was read; R1's probe shape re-applied to
`config.py` and reverted; **two throwaway Hubs driven from source** (ports 8093 and 8094, fresh
profile directories under `testbed/scratch/f388r2/`, killed by exact PID, never `:8000`/`:8010` and
never `~/.agentweave/hub/data/`). **R1's four named weak points all survive, three of them with
their reasoning corrected** - and R2 found four things R1 did not, marked **R2** below. Nothing R1
decided is re-opened; what changed is what the document claims while deciding it.

| R1 asked R2 to attack | R2's verdict |
|---|---|
| **D9** - does (a)+(b) remove the route or narrow it? | **Removes it.** No remaining launch reaches the live database with no `DATABASE_URL` - measured, D9 below. |
| **D5** - measured by hand-calling `fileConfig`, not from a running Hub | **Holds, now driven.** 104 alembic `INFO` lines, **zero** `hub.*` `INFO` lines. Plus a detail R1 could not see: D5 below. |
| **D3** - does a `.env` count as "told"? | **Yes, unchanged** - but D3's *consequence* about `.env.example` was wrong, and R1's fix for it would have broken Docker. |
| **D4** - rejected on a *reasoned* version-skew argument | **Conclusion holds; its premise was false.** There **is** a dependency edge. Corrected below, and the corrected version argues D4 harder. |

R2 also corrects the blast radius (the CLI suite and a second script), and narrows two scenarios in
the delta that the code falsifies as written. Four new tasks: 1.9, 3.5, 4.9, and the rewritten 4.7.

---

## D11 — what the resolver returns today, and what each caller does with it

The round was asked for this table first, because every decision below is a decision about one of
its rows. `Settings()` is `hub/hub/config.py:45`, a module-level singleton, so every row happens at
**import time of `hub.config`**, before any caller has a chance to check anything.

| `DATABASE_URL` | `Settings().database_url` returns | what the callers do with it |
|---|---|---|
| absent, no `.env` in cwd | `sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/data/agentweave.db` | `engine.py:36-40` builds an engine on **the operator's live database**; `init_db` migrates it |
| absent, cwd = `hub/` | `sqlite+aiosqlite:///data/agentweave.db` — **relative**, from `hub/.env:5` | resolves against the process cwd (`…/AgentWeave/hub/data/agentweave.db`) |
| `""` (set but empty) | `''` | `create_async_engine('')` → `ArgumentError: Could not parse SQLAlchemy URL from given URL string`, **at `engine.py:36`, i.e. import** |
| `"not a url at all"` | `'not a url at all'` | same `ArgumentError`, same place |
| valid URL, **file** does not exist | the value, unchanged | SQLite **creates** it on first connect; the full migration chain runs; indistinguishable from success |
| valid URL, **directory** does not exist | the value, unchanged | `init_db` calls `os.makedirs(dir_part, exist_ok=True)` (`engine.py:346-350`) and then creates the file |

Four consequences the rest of this document leans on:

1. **`database_url` is a plain `str` with no validator.** The resolver validates nothing; the only
   check in the system is SQLAlchemy's URL parse, and it happens at import of `hub.db.engine`.
2. **Malformed is the safe case.** It fails loudly, at import, before a connection exists. The
   dangerous cases are the ones that *succeed*.
3. **There is no path the Hub refuses.** Directory missing → it makes one. File missing → SQLite
   makes one. A typo does not fail; it silently forks a second database. This is why (a) has to act
   on *absence of instruction*, since it cannot act on *badness of path*.
4. **The relative row is live, not hypothetical.** `hub/.env` on this machine carries it, copied
   from `hub/.env.example:5`. **R2:** that value is the *container's* default and is correct there
   (`WORKDIR /app` + the `hub-data` volume at `/app/data`) - it is not, as R1 called it, the pre-`D1`
   bug still shipped; it is a container default in a source checkout. See D3. **R2, measured:**
   `hub/data/` does not exist on this machine, so this row is reachable in code but no start has
   yet taken it here.

---

## D1 — the refusal lives in `config.py`, not in `main.py`

`settings.database_url` is read outside `config.py` by three Hub modules — `hub/hub/db/engine.py`
(`:37`, `:39`, `:199`, `:218`, `:228`, `:346`, `:347`, including the module-level
`create_async_engine` that begins at `:36`), `hub/hub/instance_identity.py:39-40`, and
`hub/hub/migrations/env.py:34,95,98` — plus `hub/tests/*`. A guard placed in `main.py`'s `lifespan()`
would be bypassed by all of `alembic upgrade`, `scripts/drive/*` and `refresh_ui_bundle.py`, which
import `hub.config` (directly or transitively) without ever constructing the app.

`Settings()` is the one point every route passes through. **The refusal goes there.**

## D2 — the mechanism is a raising `default_factory`, not a required field

Three shapes were considered, and two were probed by patching `config.py` for real and running the
affected commands:

| shape | what an operator sees | verdict |
|---|---|---|
| `database_url: str` (required) | `pydantic_core.ValidationError: 1 validation error for Settings / database_url / Field required [type=missing, input_value={}, input_type=dict]` — **measured verbatim** | **rejected.** Names neither the database refused nor either way to set it. It is the error pydantic would give for a typo in a field name. |
| `field_validator` on the value | never runs when the field is absent | rejected — validators do not fire for a missing value |
| `default_factory=_refuse_to_guess` that raises | a `RuntimeError` subclass carrying whatever sentence we write | **chosen** |

Measured about the chosen shape, on `pydantic-settings` as installed here:

- the exception **propagates unwrapped** — `HubNotToldWhichDatabase`, not a `ValidationError`
  wrapping it — so the message is the whole output and not the innermost line of a validation
  report;
- the factory **does not run at all** when any source supplied a value (env var *or* `.env`), so
  this adds no cost and no behaviour change to every supported launch path;
- it still leaves `_default_database_url()` a live, callable function, which D7 needs.

**The message is part of the change, not decoration.** It must name (1) the path it refused to open,
spelled out absolutely, (2) `DATABASE_URL=…` as the way to say what to open, and (3) bare
`agentweave` as the way to get the default deliberately. Task 1.4 pins the message; task 1.5 asserts
all three in a test, because a message nobody asserts is a message that decays.

## D3 — "not told" means: nothing in the environment, and nothing in a `.env`

`SettingsConfigDict(env_file=".env")` (`config.py:21`) resolves a **relative** filename against the
process working directory. So a `uvicorn hub.main:app` from `hub/` reads `hub/.env`, and the same
command from the repository root reads the repository root's `.env` (which exists and does *not* set
`DATABASE_URL`).

**A `.env` value counts as being told.** It is a file someone wrote deliberately, pydantic-settings
treats it as a source, and the measured behaviour is that it satisfies the factory. Ruling otherwise
would mean refusing Docker mode, which supplies the variable through
`hub/docker-compose.yml:31-34`'s `env_file` + `environment`.

Two consequences carried as tasks rather than argued away:

- **`hub/.env.example:5` ships a relative path**, and it is what `hub/.env` was copied from. A `.env`
  that satisfies the refusal while naming a cwd-dependent file reintroduces the launch-directory
  dependence D1 of `2026-08-16-one-hub-and-a-window-of-its-own` removed.
- **The refusal message must say which sources were consulted**, or an operator who *has* a `.env`
  one directory up will read the message as false. Task 1.4.

**R2 - the `.env.example` half of that was wrong, and the fix R1 wrote for it would have broken
Docker.** R1 called `hub/.env.example:5` "the pre-`D1` bug, still shipped" and had task 4.7 make it
absolute. Measured, `.env.example` is **the container's** template and its relative value is correct
there:

- `hub/Dockerfile:11` sets `WORKDIR /app` and `hub/docker-compose.yml:23` mounts the named volume at
  `/app/data`, so `sqlite+aiosqlite:///data/agentweave.db` resolves to `/app/data/agentweave.db` -
  which is the volume. An absolute *host* path there names nothing inside a container.
- `.env.example:4`'s own comment already says so: *"(default: `data/agentweave.db` **inside the
  container**)"*.
- It is **inert in the documented install anyway**: `docker-compose.yml:31-34` supplies the same
  value under `environment:`, which takes precedence over `env_file:`, and compose's own comment
  (`:13-14`) says the documented install is this file curled alone into an empty directory.

So `.env.example` is not the pre-`D1` bug. It is a container default that is right for containers
and **wrong the moment somebody copies it into a source checkout** - which is exactly what `hub/.env`
on this machine is. Measured: from `hub/`, `Settings()` returns
`sqlite+aiosqlite:///data/agentweave.db`, i.e. `hub/data/agentweave.db`; and `hub/data/` **does not
exist on this machine**, so that branch of the resolver is live in code but has never yet been the
path a start actually took here.

The task therefore **adds a comment**, it does not absolutize (rewritten 4.7), and the delta's
scenario *"The database a launch path names does not depend on its working directory"* is narrowed
(task 5.2): as R1 wrote it, it required *any* environment file shipped with the Hub to carry an
absolute path, and was therefore falsified by the Docker configuration being **correct**.

## D4 — refusing the default *path* (not just the implicit default) was considered and rejected

The stronger guard — refuse `~/.agentweave/hub/data/agentweave.db` even when `DATABASE_URL` names it
explicitly, unless an opt-in variable is set — would also cover the typo and copy-paste routes, and
it needs no migration, so it escapes the objection that killed **(c)**.

**It is rejected, and the reason is not caution.** `src/agentweave/cli.py:1028` sets
`os.environ["DATABASE_URL"]` to **exactly that path** for the default profile before importing
`hub`. A path-keyed refusal therefore refuses the operator's own app, and distinguishing "the CLI set
it" from "a human typed it" requires the CLI to pass a marker - and the two distributions can sit at
different versions on one machine. An older installed CLI would not set the marker, and the
operator's app would stop starting after a Hub upgrade. **Trading an A that fires on agents for an A
that fires on the operator is not an improvement**, and the version skew is not detectable from
inside the Hub.

Recorded so R3 does not re-raise it. If it is ever revisited, the missing piece is a CLI-side change,
which is a different distribution and a different change.

**R2 - D4's conclusion stands, but it was resting on a false sentence, and the true one argues it
harder.** R1 wrote that `agentweave-ai` and `agentweave-hub` are *"independently installable
distributions with **no dependency edge** between them"*. **There is an edge**: `pyproject.toml:34`
is `dependencies = ["agentweave-hub>=1.1.0"]`, and `CLAUDE.md` states it as the CLI's one runtime
dependency. R1 did not invent the claim - the same false sentence is in the docstring of
`hub/tests/test_config.py:56-58`, which R1 read and carried forward. Task 1.9 fixes it there too, so
the next round to read that file is not misled the same way.

The corrected fact is **worse for a CLI-sent marker, not better.** The edge is a floor with no
ceiling, and both distributions sit at `1.1.0` today (`pyproject.toml:7`, `hub/pyproject.toml:7`), so
`pip install -U agentweave-hub` yields a **newer Hub with an unchanged `agentweave-ai` that still
satisfies `>=1.1.0`** - precisely the skew direction that would leave the operator's app unable to
start. An edge that only sets a floor does not make two versions move together; it only guarantees
the Hub is present. `TestDatabaseUrlDriftAgainstCli` (task 1.7) remains the right guard for the right
reason: the two path computations are independent code, whatever the packaging declares.

## D5 — (b) is a `WARNING`, and this is the load-bearing decision of the whole change

Measured, in a process with nothing else configured (which is what plain `uvicorn hub.main:app` is):

```
before init_db : root handlers = []            root level = 30 (WARNING)   → INFO dropped, WARNING printed by logging.lastResort
after  init_db : root handlers = [StreamHandler(stderr)]  root level = WARNING
logging.getLogger("hub.db.engine").isEnabledFor(logging.INFO)  →  False
```

The `after` state comes from `hub/hub/migrations/env.py:14-28`, which runs `fileConfig` against
`hub/hub/alembic.ini`, whose `[logger_root]` is `level = WARN, handlers = console`
(`alembic.ini:20-22`). **The Hub configures no logging of its own** — `main.py` only calls
`logging.getLogger(__name__)`.

So `hub/hub/db/engine.py:228` — `logger.info("Alembic migrations applied to %s",
settings.database_url)`, **the one line in the tree that already names the database** — has never
been emitted to anyone, in either state. Writing (b) as `logger.info` would produce a second such
line and a green test, which is this repository's named dominant failure mode.

**(b) is `logger.warning`.** It is not a warning about a problem; it is the one fact that is worth
more than the level it has to be emitted at to exist. Task 2.4 records that reasoning in the code, so
that a later tidy-up does not "correct" it back to INFO.

**R2 - driven, from a real `uvicorn hub.main:app`, which is what R1 asked for.** Two throwaway Hubs
from source against fresh profile directories, full `0001→0104` migration chain both times:

| what was emitted | where | appeared? |
|---|---|---|
| `hub.db.engine` `logger.info` - the existing `:228` line | after migrations | **no** - 0 occurrences in 108 lines of output |
| `hub.db.engine` `logger.info` probe | before `init_db`'s first write | **no** |
| `hub.db.engine` `logger.warning` probe | before `init_db`'s first write | **yes** |
| `hub.db.engine` `logger.warning` probe | after migrations | **yes** |

Every one of the 104 `alembic.runtime.migration` `INFO` lines appeared, which is what makes the
absence of the `hub.*` ones evidence rather than an empty log. **D5's conclusion survives a real
drive: (b) must be `WARNING`.**

**And one thing a hand-called `fileConfig` could not have shown, which changes what task 2.2 must
specify.** At D6's chosen site - before `init_db`, therefore before `fileConfig` - the line is
emitted by `logging.lastResort`, which has **no formatter**. Measured verbatim, the same warning
prints differently in the two states:

```
before init_db :  PROBE-PREWRITE-WARNING sqlite+aiosqlite:///C:/.../agentweave.db pid=28980
after  init_db :  WARNI [hub.db.engine] PROBE-POSTMIGRATE-WARNING sqlite+aiosqlite:///C:/...
```

So at the site (b) is going to, the line carries **no level, no logger name and no timestamp - just
the message**. It cannot lean on a `WARNING [hub.main]` prefix to announce what it is; the sentence
itself has to. Task 2.2 now requires that.

*A rejected alternative, recorded:* have the Hub configure its own logging so INFO is visible.
Correct, larger than this change, and it collides with the F151 comment in `migrations/env.py` that
deliberately leaves uvicorn's configuration alone. Out of scope; **not** filed as a finding, because
the F151 comment already states the position.

## D6 — where the line goes: `lifespan()`, before `await init_db()`

Three candidate sites, in order of earliness:

1. `config.py` module scope, after `settings = Settings()` — earliest, but fires for every importer,
   including `pytest`, `alembic`, and `make ui`. Rejected: a line that appears in unrelated tool
   output is a line people learn to skip.
2. `engine.py` module scope, before `create_async_engine` — rejected for the same reason
   (`conftest.py` imports it) and it buys nothing: **`create_async_engine` does not connect.**
3. **`main.py`'s `lifespan()`, as the first statement, before `await init_db()` — chosen.**

(3) is still before anything is opened or written: `init_db` is where `os.makedirs` runs
(`engine.py:346-350`), where `Base.metadata.create_all` runs, and where `_run_alembic_upgrade` runs.
Naming the file after `init_db` would name a file this process has already modified — which is the
difference between a warning and a receipt.

**What the line carries, and one thing it must not claim.** The resolved **absolute** path; whether
that file **existed before this process opened it** (`Path(...).exists()`, evaluated before
`init_db`); and `os.getpid()`. It must **not** print a port: `settings.aw_port` is configured intent
and `hub/hub/main.py:540` is the only thing that honours it, while `--port` on the command line never
reaches `settings` — `hub/hub/bound_address.py` exists precisely because of that divergence, and it
is **empty during `lifespan()`** (it is populated by request middleware, `main.py:466-469`). A line
that printed `aw_port` would name the wrong port in exactly the drive scenario F388 came from.

The "existed before" half replaces an inference with a fact: `DEAD-ENDS.md` currently tells a driver
to infer a wrong attachment from the *absence* of a migration chain in the log. Absence is not a
safeguard; this makes it a presence.

**R2 - "before the first write" is true of the launch path this change is for, and false of the other
two. Say so rather than letting the delta claim it universally.** Both production launch paths apply
migrations in a step that never reaches `lifespan()`:

- **native `agentweave`** runs `_hub_run_migrations(hub_pkg_dir)` at `src/agentweave/cli.py:1054`
  (step 7, "Running database migrations...") and only then spawns uvicorn (step 8);
- **Docker** runs `alembic -c hub/alembic.ini upgrade head && uvicorn hub.main:app` as one `CMD`
  (`hub/Dockerfile:31`), so the file is created and migrated by a *separate process* first.

For those two, (b) names a database this install has already written to - a receipt, which D6 itself
says is the thing it is trying not to be. For a direct `uvicorn hub.main:app` - **the launch F388
happened on, and the only one an unattended window uses** - it is genuinely before the first write.
That is enough for the change to do its job, and it is not enough for the delta's scenario as R1 drew
it (*"before it creates a directory, creates a file, or applies a migration to it"*, over a `WHEN`
that included bare `agentweave`). Task 5.2 narrows the scenario to the launch path the site can hold
for; `lifespan()` stays the chosen site, because moving the line earlier costs more than it buys
(candidates 1 and 2 above, still rejected for the same reasons).

## D7 — `_default_database_url()` survives as a function

Removing the default value is not removing the path. It is still needed three times:

- the refusal message quotes it ("I would have opened `…`; say so explicitly if you meant it");
- `hub/tests/test_config.py::TestDatabaseUrlDriftAgainstCli::test_hub_default_matches_cli_hub_dir`
  compares it against `agentweave.cli.HUB_DIR`, guarding the two-distribution seam D4 leans on. That
  guard must keep a subject;
- `agentweave doctor` reports on that path, and `doctor` must keep working (measured: it does not
  import `hub`, so it is unaffected either way).

Measured under the probe: with the field made required, **`test_default_is_absolute_home_relative_path_not_the_old_relative_default`
and `test_hub_default_matches_cli_hub_dir` both fail** (`2 failed, 2 passed`). Group 1 rewrites the
first to assert the *refusal* and repoints the second at the function. **Neither is deleted** — the
second is the only thing guarding the seam.

## D8 — this change reverses a current requirement, and says so

`openspec/specs/app-lifecycle/spec.md` currently requires, normatively:

> The one local AgentWeave runtime SHALL resolve to the same database and instance state regardless
> of which directory it was launched from, whether started through bare `agentweave` (with or without
> `--docker`/`--local`), a direct `uvicorn hub.main:app` invocation, or `docker compose up` …

with the scenario **"The Hub's own database is launch-directory-independent"** spelling out *"a
direct `uvicorn hub.main:app` invocation **with no `DATABASE_URL` set**"* landing on the home path.

**That sentence is F388.** The guarantee it was written for is real — the original bug was a
cwd-relative default producing a *different* database per launch directory — but it was discharged
by making the *unspecified* case resolve somewhere, when what it needed was for the unspecified case
to not exist. The delta keeps the launch-directory-independence guarantee for every launch path that
says which database it wants, and replaces the no-`DATABASE_URL` scenario with a refusal scenario.

Docker Compose's scenario is untouched: `hub/docker-compose.yml:31-34` sets the variable, so it is a
told path, not an implicit one.

## D9 — the third loss: what (a) and (b) reach, and what is left standing

F388 is an **A** because of its third loss — *the recovery is worse than the fault*. An agent that
discovers it is on the live database had no safe way to detach, and the blanket
`taskkill /IM python.exe /T` it reached for took the operator's app down for about three hours.

Honestly stated:

- **(a) removes the route that produced the incident.** The 2026-09-19 attachment happened because
  the variable was absent; absent now refuses. A recovery that is never needed is better than a safe
  one.
- **(b) shortens the window.** The attachment becomes readable in one line *before the first write*,
  instead of being inferred afterwards from a missing migration chain. An agent that reads it at
  second zero has a Hub that has opened a file and modified nothing.
- **(b) also makes the safe kill possible**, which is why `os.getpid()` is on the line: the recovery
  is "kill the PID this process printed", and failing that `netstat -ano` on the port, never a
  blanket `taskkill /IM python.exe`. Task 4.2 moves that from `DEAD-ENDS.md` — where it is one
  window's lesson — into `.claude/reference/hubs.md`, where it is the documented procedure. Note
  `taskkill /IM python.exe` does **not** match `pythonw.exe`, and the operator's app is
  `pythonw`-hosted, so "no python is running" was never evidence it survived.

**Left standing, deliberately:** a Hub that is *already* attached still has no in-product detach -
no endpoint, no signal, no "this is the wrong database, close it" path. That would be a change to
`main.py`'s shutdown surface, not to `config.py`, and the operator scoped this one to
`hub/hub/config.py` + tests + prose. **R2 and R3 should check this section hardest**: if (a) + (b)
do not in fact remove the route, the severity argument in the proposal is wrong and the change is
under-scoped.

### R2 - the question R1 posed, answered by measurement: name a launch that still reaches the live database with no `DATABASE_URL`

**There is none.** R1's probe shape (a `default_factory` that raises instead of returning the home
path) was re-applied to `config.py`, which makes the question safe to ask directly: every route that
*would have* opened the live database instead names it in an exception. Measured:

| launch | with (a) in place | reaches `~/.agentweave/hub/data/agentweave.db`? |
|---|---|---|
| `uvicorn hub.main:app` from a cwd with no `.env` | raises, naming the absolute home path, **unwrapped** | **no** |
| `uvicorn hub.main:app` from `hub/` (this machine) | `hub/.env` supplies a value, so (a) never fires | **no** - it resolves to `hub/data/agentweave.db` |
| `uvicorn hub.main:app` from `hub/` on a **fresh checkout** | `hub/.env` is gitignored (`.gitignore:69`) and absent, so (a) fires | **no** |
| bare `agentweave` | `cli.py:1028` sets the variable to that path on purpose | **yes, and correctly** - told, not guessed |
| `docker compose up` | `docker-compose.yml:34` sets it | n/a - container path |
| `make ui` / `refresh_ui_bundle.py` | raises today; task 3.1 points it at `:memory:` | **no** |
| `scripts/drive/n10_route_reachability.py` | raises today; task 3.5 points it at `:memory:` | **no** |

The third row is the one that matters most and R1 did not draw it. `hub/.env` is **gitignored**, so
the file that currently absorbs a missing `DATABASE_URL` from `hub/` **does not exist in a clean
checkout** - which means the launch `CLAUDE.md` itself instructs (*"Start it from `hub/`, from
source"*) lands on the home default on any machine that has not hand-made that file. That is the
route, it is reachable from the repository's own documented procedure, and (a) closes it.

**One residue, and it is D3's rule working as intended, not a gap:** a `.env` in the launch directory
that names the home path *would* still be honoured. That is "told" by D3's definition, and refusing
it is the path-keyed guard D4 rejects for reasons R2 has since strengthened. Nothing on this machine
does it (`hub/.env` names the relative container path; the repository root's `.env` sets no
`DATABASE_URL` at all - both read).

## D10 — one sentence in `DEAD-ENDS.md`'s F388 practice is false, and is corrected rather than dropped

The entry says:

> `sqlite3`/`aiosqlite` will not create a missing parent directory, so a silent fallback to the
> default is also what a *correct* URL against a missing directory would look like from a crashed
> start, making directory-existence the cheap thing to check first.

**True of raw `aiosqlite`** — measured: connecting to a URL whose parent directory is missing raises
`OperationalError: (sqlite3.OperationalError) unable to open database file`. **False of the Hub**:
`init_db` runs `os.makedirs(dir_part, exist_ok=True)` before the first connect
(`engine.py:346-350`), so the Hub creates the directory it was pointed at.

The *practice* survives and gets stronger. Under the Hub's real behaviour, a named profile directory
that does **not** exist after a start is no longer ambiguous between "crashed" and "fell back": the
Hub would have created it, so its absence proves **the URL never reached the process at all**. Task
4.1 rewrites the sentence and keeps the check.

---

## What R1 asked R2 to attack, and what R2 returned

R1's four items are answered in place, above: **D9** (route removed - the measured table), **D5**
(driven from two real Hubs; conclusion holds, one new constraint on task 2.2), **D3** (the judgement
call stands; its `.env.example` consequence was wrong and its fix would have broken Docker), **D4**
(conclusion stands; the premise was false and the true one is worse for the rejected option).

**R2's own four, none of which R1 had:**

1. **The blast radius is bigger than "`refresh_ui_bundle.py` only".** Measured under the probe, the
   **CLI suite** breaks too: `tests/test_hub_commands.py::test_first_start_migrations_leave_a_database_that_can_hold_a_conversation`
   does a bare `import hub.config` at `:707` with no `DATABASE_URL`, and the module-level
   `Settings()` raises before its own `patch.object(settings, "database_url", ...)` can help. Exactly
   one new failure: `py -3.11 -m pytest tests/ -q` gives `3 failed, 532 passed, 3 skipped` under the
   probe, and **two of the three are pre-existing** (`test_skill_sync.py`, confirmed failing on a
   clean tree). New task 4.9; the proposal's Impact is corrected.
2. **A second script caller.** `scripts/drive/n10_route_reachability.py:119-121` runs
   `subprocess.run([sys.executable, "-c", "from hub.main import app..."], cwd=REPO / "hub")` with no
   `DATABASE_URL`. It survives here only because the gitignored `hub/.env` exists; it wants routes,
   not a database, so it belongs with 3.1 rather than with the drive scripts that are *correct* to
   fail. New task 3.5.
3. **Two scenarios in the delta are falsified by the code being right.** The environment-file
   scenario is falsified by Docker's relative path being correct (D3), and the
   named-before-it-is-opened scenario is falsified by native `agentweave` and Docker migrating before
   `lifespan()` runs (D6). Task 5.2 narrows both.
4. **The false "no dependency edge" sentence is in the test file too**, not only in D4
   (`hub/tests/test_config.py:56-58`). New task 1.9.

## Round 3 — what R3 attacked, and what it found

R3 read the code before the document, took the four targets R2 named, and **ran** the probe R1 and
R2 only reasoned from. **Every decision in this change survives a third time** — (a), (b), (d), the
`config.py` site, the raising `default_factory`, the `WARNING` level, the `lifespan()` site, D4's
rejection of a path-keyed guard, and the `MODIFIED` delta. No decision was reopened. What follows is
one confirmation, one defect, and one completed measurement.

**1. The narrowed delta is right, not convenient — and the reason is stronger than R2's.**
R3 re-derived both narrowings from `hub/Dockerfile:31`, `hub/docker-compose.yml:23,34` and
`src/agentweave/cli.py` *before* reading R2's text, and reached the same conclusions independently:
the container's relative path is correct (`WORKDIR /app` + `hub-data:/app/data` + an `environment:`
key that overrides `env_file:`), and both native `agentweave` and Docker migrate in a separate step
before `lifespan()` runs. R3 then found what R2 did not: `_hub_resolve_database_source`
(`cli.py:599-616`) returns `message=None` for the **default** profile. A plain `agentweave` start
therefore names its database **nowhere** before `_hub_run_migrations` (`:1054`) opens it; only a
named `--profile` prints a path, and it prints it at `:1026`, before the migration. So R1's broad
scenario was not merely unproven on the native path — it was **unsatisfiable there without changing
the CLI**, which this change does not touch. Narrowing was the only honest move.

**2. One real defect: the delta contradicted its own tasks.** R2's scenario *"A container's own
relative database path is not a host path"* covered *"an environment file **or compose file**"* and
required *the file* to state that its value is a container path. `hub/docker-compose.yml:34` carries
no such statement, and **task 4.8 explicitly forbids changing it** — so the change shipped a
normative clause its own task list refused to satisfy. Fixed: the stating-clause is now scoped to a
file that is *a template intended to be copied*, which is `hub/.env.example` (task 4.7) and not the
compose file. This is the defect R2's own note predicted would be there — the narrowing was R2's
weakest work not because it narrowed too much, but because it widened one clause while narrowing
another.

**3. Group 3 is now measured rather than read, and it is complete.** R3 applied the raising
`default_factory` **with `hub/.env` moved aside**, so what was measured is a *clean checkout* rather
than this machine. Every `hub.*` import under `scripts/` was resolved by running
`importlib.import_module(m)` and asking whether `hub.config` landed in `sys.modules`; the full
result is in task 3.2. Three outcomes worth naming here:

- **The two known breaks are confirmed by running them,** not by reading: `refresh_ui_bundle.py`
  (`make ui`, `make ui-check`) and `n10_route_reachability.py` both die with the probe's exception.
  The CLI suite's cost is **exactly one test**, and R3 captured its name where R2 had only a line
  number: `test_first_start_migrations_leave_a_database_that_can_hold_a_conversation`
  (`pytest tests/test_hub_commands.py -q` under the probe: `1 failed, 40 passed`).
- **Both CI jobs are unaffected, measured.** `ci.yml:61` and `ci.yml:131` (`import agentweave, hub`
  from `hub/`) exit 0 — `hub/hub/__init__.py` reads package metadata and never imports `hub.config`
  — and both suites collect clean. **Collection is the wrong instrument**, which is itself the
  finding: the CLI break is an `import hub.config` inside a test *body*, invisible to
  `--collect-only`. A future round must not mistake a green collection for a green run.
- **Nothing in CI guards either fix.** `grep -rn "refresh_ui_bundle\|ui-check\|make ui"
  .github/workflows/` returns nothing. Tasks 3.1 and 3.5 are protected only by a human running them,
  which is why 3.6 now says so and why `os.environ.setdefault` is the right shape.

Also measured and deliberately *not* filed as blast radius: a bare `alembic -c hub/alembic.ini` from
`hub/` with no `DATABASE_URL` raises, because `migrations/env.py:10` imports `settings`. That is the
change **working**. Docker and native both set the variable before migrating, and no documented
workflow runs alembic bare — `.claude/rules/db-migrations.md` does not, and
`.claude/skills/copilot-test-setup/SKILL.md:73` sets `$env:DATABASE_URL` first. Recorded so a fourth
reader does not re-open it.

**4. Task 2.2 holds, and R3 closed the gap underneath it.** 2.2's requirement — that the line
identify itself in its own words, because at this site there is no `WARNING [hub.main]` prefix — is
consistent with 2.1's placement before `await init_db()` and with 2.4's `logger.warning`. But the
delta's clause *"names what it is without depending on a logger-name or level prefix being present"*
was the one normative sentence in the change with **no task verifying it**: 2.6 asserted `levelno`
and text, and `caplog.text` interpolates exactly the prefix this site does not have. 2.6 now asserts
against `record.getMessage()` alone.

**5. The proposal's "Why" — a note for the operator, not a decision.** R2 softened the "from `hub/`"
sentence and flagged it; R3 did not re-derive F388's cause (DIRECTION item 2 forbids it) and reports
only this: **the discrepancy is not load-bearing for this change.** The case for (a) rests on
`config.py:23` making a missing variable indistinguishable from a deliberate one, on the docstring
naming the dangerous path as the safe one, and on nothing downstream ever refusing a path. None of
those depends on which directory the 2026-09-19 start ran from, and (a) refuses whichever path the
default would have named. It *is* load-bearing for one thing: the `DEAD-ENDS.md` entry group 4
rewrites is advice to a future agent, and it must not assert a launch directory the finding does not
establish. Task 4.2 now carries that as a guard over the whole group. Whether the incident's cwd is
worth establishing at all is the operator's call.

**Nothing else changed.** R3 reopened no decision, added no task outside group 3, and left every
number, level, site and rejection exactly where R1 and R2 put them.

## Round 4 — the verification round after the Opus DO NOT APPROVE (2026-09-21)

**Why a fourth round.** The operator's standing adversarial Opus pass ran on 2026-09-20 and returned
**DO NOT APPROVE**, with four blocking items and one unreconciled premise (`spec-queue/APPROVALS.md`
§ *REVISING*). R4 was run by a session that wrote none of R1–R3. It took the reviewer's items as
targets, not as conclusions, and re-derived each from the code. **Every decision survives a fourth
time:** (a), (b), (d), D1–D11 and the `WARNING` level. The core mechanism was never in question, and
the reviewer could not break D2 or D3 either. **All four blockers are real, and all four are in the
tasks and the delta.** Two findings go beyond what the reviewer reported.

**1. The delta contradicted itself (blocker 1): confirmed and fixed.** The first paragraph of the
modified requirement still required *"a direct `uvicorn hub.main:app` invocation"* to resolve to the
same database from any directory. D3 makes a `.env` a told source, and task 4.7 keeps
`.env.example`'s value relative. So a direct launch from `hub/` with a copied `.env` resolves
cwd-relative, and does so correctly. The paragraph now scopes directory-independence to **launch
paths that choose a database for themselves**: bare `agentweave`, `--profile`, and `docker compose`.
It states that a direct `uvicorn` opens exactly what it was told, a relative value included, because
that is the operator's instruction and not the runtime's guess. The paragraph that follows was
reworded to refer back to it. `openspec validate --strict` passes. Only the requirement's first
physical line counts for `SHALL`, and that line is unchanged.

**2. Task 2.7 could not fail (blocker 2): confirmed, and the mechanism is plainer than "the pytest
plugin".** The Hub suite runs on `:memory:`, and `engine.py:199` skips the alembic upgrade for it, so
`migrations/env.py:28`'s `fileConfig` **never runs under `pytest`**. The "alembic-configured root" the
test names does not exist there. What the test sees is Python's default `WARNING` root, and the
assertion holds whatever the Hub's logging does. R4 replaced it with the test D5 actually wanted:
- a real `uvicorn hub.main:app --port 0` in a subprocess, on a `tmp_path` database with `cwd=tmp_path`;
- it reads `stderr` until `startup complete` (**4.4 s, measured**);
- it asserts the line appears before the first `Running upgrade`.

That test fails under `logger.info`, which is the mutation that matters, and it does not care whether
`alembic.ini` exists (task 2.7). The same shape, with `USERPROFILE`/`HOME` pointed at a throwaway
directory, turns 6.1's refusal into a regression guard that never names the operator's home (new
task 2.8). This retires the claim, carried since R1, that *"no unit test can make"* that check.

**3. Group 3 was complete for imports and blind to launches (blocker 3): confirmed, and worse.** R3's
sweep asked *which `scripts/` import `hub.config`*. The reviewer's three misses are not imports.
They are **launches**: two skills plus their `.agents/` mirrors, and `make dev`. R4 ran the launch
sweep (task 3.7). The finding the reviewer did not have: the two skills start `:8010` from `hub/` with
no variable, so they read `hub/.env`, whose relative value resolves to **`hub/data/agentweave.db`**.
That is not the trial profile at all, and `hubs.md:22` records that file as deleted on 2026-09-07.
**Today those skills open, and silently re-create, a third database. That is F388's own shape, live on
this machine, and not only a clean-checkout problem.** `make dev` needs no code change: with a
copied `.env` it is a told launch, and without one it refuses before migrating, which is correct.

**4. Remedy (d) left a live copy (blocker 4): confirmed.** The `hub/tests/test_config.py:1-7` module
docstring restates the removed guarantee (new task 4.10). 4.1's replacement text was unqualified in
the same way, because `cli.py:617-621` passes a pre-existing `DATABASE_URL` through (4.1 amended).
**R4 found a third copy, and it is user-facing:** `docs/getting-started/installation.md:52-62` tells
readers that a direct `uvicorn` launch is *"fixed going forward"* onto the shared database. That
page ships to GitHub Pages (new task 4.11). No earlier round swept `docs/`.

**5. The `:8000` premise: reconciled by measurement, and the doc is false.** Every earlier round
asserted that `:8000` is a native `agentweave` start. The reviewer refuted the "brick" reading of
`hubs.md:37`, but did it by inference from a PID file. R4 closed it read-only, with no call to
`:8000`:
- the desktop shortcut `AgentWeave.lnk` is `pythonw.exe -m agentweave`;
- PID 9940's command line is the spawn at `cli.py:1070-1079`, which inherits the `DATABASE_URL` set
  at `:1038`. **Corrected by the R4 review:** 9940's interpreter is `python.exe`, not `pythonw.exe`,
  so it came from a terminal `agentweave` and not from the shortcut. Both routes go through the
  CLI, so the conclusion stands and the chain as first written was wrong;
- the CLI's `.env` loader only `setdefault`s.

`:8000` is a told launch, and **(a) does not brick it.** `hubs.md:36-38` is corrected under task 4.5.
The same measurement exposes a limit that the delta's *"named on every other launch path"* scenario
satisfies only on paper. The native child's `stdout` and `stderr` are `DEVNULL` (`cli.py:1096-1097`),
so on the operator's own Hub group 2's line is emitted and read by nobody. This is recorded as a
known limit rather than widened into scope. F388's launch was a direct one, where the line is seen.
Surfacing it on native starts would be a CLI change, outside this change's blast radius.

**Human-only item 5 (test guide), partly answered.** On this machine, the one non-CLI Hub starter the
operator owns is the desktop shortcut, and it goes through the CLI. The three `AgentWeave*` scheduled
tasks start loop windows, not a Hub. What will refuse after this lands are the two skill launches of
task 3.7, and that is the reason to fix them in the same commit as group 1.

**What R4 did not do.** It changed no product code and ran no suite. The subprocess measurement used
a `tempfile.mkdtemp` database, deleted afterwards, and touched no Hub.

### The adversarial Opus pass over R4 (2026-09-21): APPROVE WITH FIXES, now applied

The operator's standing step ran over `da19eb5`. **All four earlier blockers were confirmed resolved,
not reworded.** Its measurements:
- a stand-in app under the same subprocess launch showed a pre-handler `logger.warning` before
  `Running upgrade`, while the same line at `logger.info` vanished, so 2.7's mutation fails;
- the `cmd.exe` quoting in 3.7 passes the exact value through;
- `Path.home()` follows `USERPROFILE` in a Windows child process;
- nothing else in `lifespan()` touches the real home directory.

It found **one blocking item**, the same class as old blocker 4:
- `docs/reference/env-variables.md:17` documents a `DATABASE_URL` default that (a) removes;
- the **`agentweave-hub` console script** (`hub.main:run`) is a launch path that chooses no database
  and was in neither the sweep nor the delta.

Applied: the refusal scenario and the direct-launch paragraph now name the console script; 3.7
lists it; 4.11 covers the reference page; A20's grep catches the default column.

Its non-blocking items, all applied:
- 3.7 now sweeps list-form launches too (`hub.main:app\|hub.main:run`). The ten it had missed all
  set the variable, so the conclusion was right by luck;
- the `.agents/` mirrors are regenerated by `scripts/sync_skills.py`, not hand-edited;
- 2.7 drops the `alembic.ini` mutation, which fought its own ordering assertion, and requires at
  least one upgrade line;
- 2.7 and 2.8 carry the implementation traps (the stderr reader thread, a `wait()` timeout,
  `conftest.py:65`'s exported `:memory:`, and the venv-launcher PID);
- 4.7's comment is reconciled with 3.7's `make dev`;
- the `:8000` chain above is corrected;
- the requirement paragraph now qualifies bare `agentweave` by the pass-through at `cli.py:617-621`;
- the relative-value SHALL gets a test (1.6).

The pass also confirmed that nothing in the change stops `:8000` coming back up on its next restart:
no migration, no UI bundle, and a told launch.

