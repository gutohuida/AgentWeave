# Design — a Hub that was not told which database refuses to open one

**Round 1, 2026-09-20.** Everything below was measured on this machine unless it is labelled
*unverified*. The measurement scripts were throwaway (`testbed/scratch/f388/`, deleted); what they
returned is transcribed here so R2 and R3 can re-derive rather than re-run.

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
4. **The relative row is live, not hypothetical.** `hub/.env` on this machine carries it, copied from
   `hub/.env.example:5`, which still ships the pre-`D1` relative default that
   `2026-08-16-one-hub-and-a-window-of-its-own` removed from `config.py`.

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

- **`hub/.env.example:5` ships a relative path** and is what `hub/.env` was copied from. A `.env`
  that satisfies the refusal while naming a cwd-dependent file reintroduces the launch-directory
  dependence D1 of `2026-08-16-one-hub-and-a-window-of-its-own` removed. Task 4.3 makes the example
  absolute and comments why.
- **The refusal message must say which sources were consulted**, or an operator who *has* a `.env`
  one directory up will read the message as false. Task 1.4.

## D4 — refusing the default *path* (not just the implicit default) was considered and rejected

The stronger guard — refuse `~/.agentweave/hub/data/agentweave.db` even when `DATABASE_URL` names it
explicitly, unless an opt-in variable is set — would also cover the typo and copy-paste routes, and
it needs no migration, so it escapes the objection that killed **(c)**.

**It is rejected, and the reason is not caution.** `src/agentweave/cli.py:1028` sets
`os.environ["DATABASE_URL"]` to **exactly that path** for the default profile before importing
`hub`. A path-keyed refusal therefore refuses the operator's own app, and distinguishing "the CLI set
it" from "a human typed it" requires the CLI to pass a marker — but `agentweave-ai` and
`agentweave-hub` are **independently installable distributions with no dependency edge between
them** (`hub/tests/test_config.py::TestDatabaseUrlDriftAgainstCli` exists to guard exactly that
seam). An older installed CLI would not set the marker, and the operator's app would stop starting
after a Hub upgrade. **Trading an A that fires on agents for an A that fires on the operator is not
an improvement**, and the version skew is not detectable from inside the Hub.

Recorded so R2 and R3 do not re-raise it. If it is ever revisited, the missing piece is a CLI-side
change, which is a different distribution and a different change.

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

**Left standing, deliberately:** a Hub that is *already* attached still has no in-product detach —
no endpoint, no signal, no "this is the wrong database, close it" path. That would be a change to
`main.py`'s shutdown surface, not to `config.py`, and the operator scoped this one to
`hub/hub/config.py` + tests + prose. **R2 and R3 should check this section hardest**: if (a) + (b)
do not in fact remove the route, the severity argument in the proposal is wrong and the change is
under-scoped.

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

## What R2 and R3 should attack first

1. **D9.** The whole severity argument rests on (a) + (b) removing the route rather than narrowing
   it. Name a launch that still reaches the live database with no `DATABASE_URL`.
2. **D5's measurement.** It was taken with a script that called `fileConfig` by hand, not from a
   running Hub. If a real `uvicorn hub.main:app` shows `hub.*` INFO lines, D5 is wrong and (b)'s
   level is over-specified. **Drive it; do not re-read this table.**
3. **D3.** Whether a `.env` should satisfy the refusal is the one judgement call here, and it is the
   difference between "told" and "told by someone who is still in the room".
4. **D4.** Rejected on a version-skew argument that was *reasoned*, not measured. If the CLI and Hub
   are in practice always installed together, the argument is weaker than it reads.
