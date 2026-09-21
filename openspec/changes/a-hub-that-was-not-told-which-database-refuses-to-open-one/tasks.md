# Tasks — a Hub that was not told which database refuses to open one

**Round 1, 2026-09-20. Round 2, 2026-09-20. Round 3, 2026-09-20. Round 4, 2026-09-21. Not approved.
Nothing here is built.**

**R4 (after the adversarial Opus pass returned DO NOT APPROVE on 2026-09-20) rewrote 2.7, 3.2 and
4.1, extended 4.5, and added 2.8, 3.7, 4.10 and 4.11.** Existing numbers are unchanged. All four
blocking items are answered here and in `design.md` § *Round 4*.

**R2 added 1.9, 3.5, 4.9 and rewrote 4.7 and 5.2.** Numbers of existing tasks are unchanged, so a
reference to "task 2.4" still means the same task it meant in R1.

**Read before starting:** this change removes a default that every unattended window on this machine
currently relies on without knowing it. **Group 3 is not optional and is not cleanup** — the moment
group 1 lands, `make ui` and every `scripts/drive/*.py` that imports `hub` stops working until group
3 is done. Do groups 1 and 3 in the same commit, or do neither.

**No migration. No `hub/ui/src` change, therefore no `make ui` bundle refresh, therefore nothing in
this change reaches the operator's live `:8000` app on their next reload.** If a task here acquires a
file under `hub/ui/src`, stop and leave it for the operator (day-window rule; the same wall
`an-archived-agent-holds-nothing-and-is-offered-nowhere` hit).

---

## Group 1 — (a): the Hub refuses to guess

- [ ] 1.1 In `hub/hub/config.py`, add a module-level exception type — `HubNotToldWhichDatabase(RuntimeError)`
      — and export it. A distinct type, not a bare `RuntimeError`: `hub/tests/` asserts on it, and a
      future caller that wants to catch this and only this needs something to name.
- [ ] 1.2 Replace `database_url: str = Field(default_factory=_default_database_url)` (`config.py:23`)
      with `Field(default_factory=_refuse_to_guess_a_database)`, a new module-level function that
      raises `HubNotToldWhichDatabase`. **Do not make the field required** — measured in D2, a bare
      required field yields `1 validation error for Settings / database_url / Field required
      [type=missing, input_value={}, input_type=dict]`, which names neither the database nor the fix.
- [ ] 1.3 Keep `_default_database_url()` exactly as it is, and call it from the refusal message
      (D7). It is still the path the CLI computes, still what `agentweave doctor` reports on, and
      still the subject of the CLI-drift test in 1.7.
- [ ] 1.4 Write the message. It MUST contain, verbatim enough to assert on: the **absolute** path it
      declined to open; `DATABASE_URL`; and bare `agentweave` as the deliberate way to get that
      default. It MUST also say which sources were consulted — the process environment **and** a
      `.env` in the working directory — because an operator with a `.env` one directory up will
      otherwise read the message as false (D3).
- [ ] 1.5 `hub/tests/test_config.py`: rewrite
      `TestDatabaseUrlDefault::test_default_is_absolute_home_relative_path_not_the_old_relative_default`
      into a refusal test. It must `monkeypatch.delenv("DATABASE_URL")`, construct
      `Settings(_env_file=None)`, assert `HubNotToldWhichDatabase` is raised, and assert **all three**
      elements of 1.4's message are present. Do not assert the whole string; assert the three facts.
- [ ] 1.6 Add the complement in the same class: with `DATABASE_URL` set, `Settings(_env_file=None)`
      returns it and **the factory does not run** (D2's measured property — assert by pointing the
      factory at something that would fail loudly, or by asserting the returned value alone if that
      reads cleaner). Also add: a value supplied only by an env *file* satisfies the refusal (D3).
- [ ] 1.7 Repoint `TestDatabaseUrlDriftAgainstCli::test_hub_default_matches_cli_hub_dir` at
      `_default_database_url()` directly instead of at `Settings(...).database_url`. **Do not delete
      it.** It is the only thing in the tree guarding the `agentweave-ai` / `agentweave-hub` seam,
      and D4's rejection of the stronger guard rests on that seam being real.
- [ ] 1.8 Run `py -3.11 -m pytest hub/tests/test_config.py -v` and record the count here. Before this
      change it is `4 passed`; under a naive required-field version it is `2 failed, 2 passed`
      (measured 2026-09-20, re-measured under R2's probe: same). **Write the number you actually
      saw**, not the number expected.
- [ ] 1.9 **(R2)** Fix the docstring of `hub/tests/test_config.py:56-58`, which states that the CLI
      and the Hub are *"independently-installable distributions with **no dependency edge** between
      them"*. `pyproject.toml:34` is `dependencies = ["agentweave-hub>=1.1.0"]` — there is an edge,
      it is a floor with no ceiling, and that is **why** the class matters: `pip install -U
      agentweave-hub` gives a newer Hub with an unchanged CLI that still satisfies the floor, so the
      two path computations really can drift. R1 read this docstring and carried its false sentence
      into `design.md` D4; leaving it fixes one copy and not the source.

## Group 2 — (b): the Hub names its database before it opens it

- [ ] 2.1 In `hub/hub/main.py`'s `lifespan()` (`:412`), as the **first statement, before
      `await init_db()`** (`:413`), resolve the sqlite file path out of `settings.database_url` and
      capture `Path(...).exists()` **into a local, before anything runs** — `init_db` creates the
      directory (`engine.py:346-350`) and SQLite creates the file, so the answer changes one line
      later.
- [ ] 2.2 Emit one line carrying: the **absolute** resolved path; whether the file existed before
      this process opened it; and `os.getpid()`. **(R2)** The line must **identify itself in its own
      words** — do not rely on a `WARNING [hub.main]` prefix, because at this site there is none.
      Measured from a running Hub on 2026-09-20: before `init_db` the record is emitted by
      `logging.lastResort`, which has **no formatter**, so it prints as the bare message; only after
      `init_db`'s `fileConfig` does the same record print as `WARNI [hub.db.engine] ...`. A reader
      seeing this line has one sentence and nothing else to tell them what it is.
- [ ] 2.3 **Do not print a port** (D6). `settings.aw_port` is configured intent — only
      `hub/hub/main.py:540` honours it, and a `--port` on the uvicorn command line never reaches
      `settings`. `hub/hub/bound_address.py` is the module that knows the real port and it is
      **empty during `lifespan()`** (populated by request middleware, `main.py:466-469`). A port on
      this line would be wrong in exactly the drive scenario F388 came from.
- [ ] 2.4 Emit it with `logger.warning`, and put the reason in a comment beside it: measured
      2026-09-20, `logging.getLogger("hub.*").isEnabledFor(logging.INFO)` is `False` both before
      `init_db` (root has no handler; `logging.lastResort` is WARNING-only) and after it (root is
      configured by `hub/hub/alembic.ini:20-22`'s `level = WARN` via `migrations/env.py:28`). Without
      the comment, a later tidy-up will "correct" the level and silently delete the feature.
- [ ] 2.5 Handle the non-sqlite case without crashing: if `settings.database_url` does not start with
      `sqlite`, log the URL **with any credentials stripped** and skip the existence check. Do not
      let the safety line become a way to print a password into a log.
- [ ] 2.6 Test it in `hub/tests/` by asserting on the emitted record (`caplog`), **not** by asserting
      the string reaches stdout — and assert the record's `levelno` is `>= logging.WARNING`. The level
      is the feature; a test that only checks the text passes on an invisible line. **(R3)** Assert
      the self-identification too, against `record.getMessage()` **alone** — not `caplog.text`, which
      interpolates a level and logger name that this site does not have (2.2). The delta requires the
      line to name what it is *"without depending on a logger-name or level prefix being present"*,
      and as R2 left it that clause was the one normative sentence in the change with no task
      verifying it.
- [ ] 2.7 **(rewritten by R4. R1's version could not fail.)** R1's test asserted
      `logging.getLogger("hub.main").isEnabledFor(logging.INFO) is False` "under the alembic-configured
      root", but no such root exists inside `pytest`. The Hub suite runs on `:memory:`, and
      `engine.py:199` skips the alembic upgrade for it, so `migrations/env.py:28`'s `fileConfig` never
      runs. Python's own default root level is `WARNING`, and pytest's logging plugin holds it there
      as well. The assertion therefore held with `alembic.ini` deleted (the reviewer ran this) and
      would hold with the site set to `logger.info`. It is the F190 shape. **Test the feature instead,
      in a real process:**
      - Launch `subprocess.Popen([sys.executable, "-m", "uvicorn", "hub.main:app", "--host",
        "127.0.0.1", "--port", "0"])` with `cwd=tmp_path`, so no `.env` is in reach, and with the env
        set to `{**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{(tmp_path / 'x.db').as_posix()}"}`.
      - Read `stderr` line by line until `Application startup complete`, with a hard timeout, then
        kill the process.
      - Assert group 2's line appears **before the first `Running upgrade` line**, says the file did
        not exist, and carries the child's PID (`proc.pid`, which 6.3 relies on).
      - Measured by R4 on 2026-09-21: this launch reaches `startup complete` in **4.4 s** and emits 110
        stderr lines (the full migration chain).
      - **Mutation check, recorded in the commit:** change 2.4's `logger.warning` to `logger.info`,
        and this test must fail. Also delete `alembic.ini`, and it must still pass, because the line
        precedes `init_db`.
      This replaces both R1's 2.7 and the unit-level proxy. 2.6 stays as the fast check on the text
      and the level.
- [ ] 2.8 **(R4)** Automate 6.1's refusal the same way, because it was the one check the change said
      no unit test could make. It can be made, safely:
      - Launch the same command with `DATABASE_URL` removed from the child env, `cwd=tmp_path` (no
        `.env`), and **`USERPROFILE` and `HOME` both pointed at a second `tmp_path` directory**.
        `Path.home()` reads `USERPROFILE` on Windows and `HOME` on POSIX, so the path the refusal
        declines is a throwaway one and the operator's real home is never named.
      - Assert a non-zero exit, and that `stderr` holds 1.4's three facts.
      - Assert **`<fake home>/.agentweave` does not exist afterwards**.
      6.1 stays as the drive, and this makes it a regression guard on Linux CI as well.

## Group 3 — the callers that break, and one of them is `make ui`

- [ ] 3.1 `scripts/refresh_ui_bundle.py:110` does `from hub.main import UI_BUILD_STAMP,
      ui_source_fingerprint` with no `DATABASE_URL` set. Measured under the probe: `make ui` and
      `make ui-check` die with a raw `pydantic_core.ValidationError`. Fix it — the script needs a
      build stamp, not a database, so set `os.environ.setdefault("DATABASE_URL",
      "sqlite+aiosqlite:///:memory:")` immediately before the import, with a one-line comment saying
      why.
- [ ] 3.2 **(R4: R3's list is complete for what it swept, and it swept only half.)** R3 swept
      *imports* of `hub.*` under `scripts/`. It never swept *launches*: every place that starts
      `uvicorn hub.main:app`. That is where the three misses were (task 3.7). Both sweeps are needed.
      Re-run both before IMPL rather than trusting either list. The imports half, as R3 measured it
      (`importlib.import_module(m)` then `'hub.config' in sys.modules`, 2026-09-20):
      - `scripts/refresh_ui_bundle.py:110` (`hub.main`) — **reaches it; breaks.** Task 3.1.
      - `scripts/drive/n10_route_reachability.py:108` (`hub.main`, in a subprocess) — **reaches it;
        breaks.** Task 3.5.
      - `scripts/drive/setup_d2_cutover.py:29-34` — `hub.checkpoint_generation` **True** and
        `hub.db.engine` **True**; breaks, and is **correct to fail**: it seeds a real database.
      - `scripts/drive/churn_sessions_plugin.py:38` — `hub.db.engine` **True**, but function-scope,
        and it wants a database; **correct to fail**.
      - `scripts/drive/t_d2_0913_f299_harness.py`, `t_d3_0913_f299_init_line.py`,
        `t_d7_0913_accept_edits_confined.py` — import only `hub.pty_runner`, `hub.runner_commands`,
        `hub.runner_parsing`, all measured **False**. **Unaffected. Change nothing.**
      - `scripts/check_model_catalog.py` — loads the catalog **by path**; 0 probe hits. Unaffected.
      Fix the first two; leave the rest; say so in the commit. If a new script appears before IMPL,
      re-run the one-liner rather than re-reasoning.
- [ ] 3.3 Confirm the launch paths that must keep working, by running them: `make ui-check`;
      `agentweave --help`; `cd testbed/scratch && agentweave doctor`. Measured 2026-09-20 that the
      last two do not import `hub` and are unaffected — **re-measure rather than trusting that line.**
      **(R3)** R3 ran the probe over both CI jobs as well, with `hub/.env` moved aside so a *clean
      checkout* was what was measured, and all of the following are **unaffected** — do not spend
      IMPL time on them:
      - `ci.yml:61` `python -c "import agentweave"` and `ci.yml:131` `python -c "import agentweave,
        hub"` (cwd `hub/`) both exit 0. `hub/hub/__init__.py` reads only package metadata; it never
        imports `hub.config`.
      - `pytest tests/ --collect-only` (538) and `pytest tests --collect-only` from `hub/` (4545)
        both collect clean. **Collection is not the instrument** — 4.9's break is an `import
        hub.config` inside a test *body*, which only a run catches.
      - `.claude/skills/copilot-test-setup/SKILL.md:73-74` sets `$env:DATABASE_URL` before
        `python -m alembic upgrade head`. Unaffected.
      Also measured: a bare `alembic -c hub/alembic.ini current` from `hub/` with no `DATABASE_URL`
      **raises**, because `migrations/env.py:10` imports `settings`. That is this change **working**,
      not blast radius — Docker sets the variable (`docker-compose.yml:34`) and native sets it
      (`cli.py:1028`) before either migrates — and no documented workflow runs alembic bare
      (`.claude/rules/db-migrations.md` does not, and the skill above sets it). Recorded so a later
      round does not re-open it.
- [ ] 3.4 Do **not** change `hub/tests/conftest.py`. It assigns `os.environ["DATABASE_URL"]` before
      importing anything from `hub` (`:57-67`), so the whole Hub suite is already a told path.
- [ ] 3.5 **(R2)** `scripts/drive/n10_route_reachability.py:119-121` runs
      `subprocess.run([sys.executable, "-c", "from hub.main import app..."], cwd=REPO / "hub")` with
      **no `DATABASE_URL`**. It survives on this machine only because the gitignored `hub/.env`
      happens to exist; on a clean checkout it already opens the home default today, and under (a) it
      will die with `could not import the Hub app`. It wants the route table, not a database — pass
      `env={**os.environ, "DATABASE_URL": "sqlite+aiosqlite:///:memory:"}` to the subprocess, with a
      one-line comment. (`:memory:` is enough: `engine.py:199` skips the alembic upgrade for it.)
      This is task 3.2's sweep done for the one entry it should not have left to judgement.

- [ ] 3.7 **(R4)** The launch sweep. `grep -rn "uvicorn hub.main:app"` over the live tree, excluding
      handoffs, archives, logs, `FINDINGS.md` and `.agentweave/tasks/` copies. Measured 2026-09-21, the
      launches that carry no `DATABASE_URL` are:
      - **`.claude/skills/e2e-loop/SKILL.md:144`**, **`.claude/skills/autonomous-session/SKILL.md:265`**,
        and both `.agents/skills/` mirrors. Each starts `:8010` from `hub/` with no variable, so today
        it survives on the gitignored `hub/.env`. **Worse than the reviewer said:** that file's value
        `sqlite+aiosqlite:///data/agentweave.db` resolves from `hub/` to `hub/data/agentweave.db`.
        That is **not** the trial profile `hubs.md:15` documents, and `hubs.md:22` records that the
        file was deleted on 2026-09-07. So these launches open, and silently re-create, a third
        database today. **Fix all four** by naming the trial profile's `DATABASE_URL` inside the
        `cmd.exe /c` string (`set "DATABASE_URL=…" && …`). After this change a clean checkout
        refuses them, and on this machine they would keep landing on the wrong file.
      - **`hub/Makefile:25` (`make dev`)** runs `alembic … upgrade head` then `uvicorn` with no
        variable. **Change no code.** On a checkout that followed `.env.example:2` ("Copy this file to .env and adjust
        values as needed"), it is a told launch that resolves to `hub/data/`, which is what a developer's `make
        dev` means. On one that did not, the `alembic` step now raises 1.4's message first, which is
        the change working. Add one comment line above the target saying so.
      Launches that already set the variable, **unaffected**: `hubs.md:28`, `CLAUDE.md:33`,
      `.claude/loops/night-window.md:235-237`, `scripts/drive/d1_0905_restart_hub.sh:13`, and the
      finished record at `openspec/changes/a-first-turn-is-not-told-it-has-nothing/tasks.md:372`.
      User-facing prose that states the old guarantee is task 4.11.
- [ ] 3.6 **(R3)** Know that **CI will not catch a regression of 3.1 or 3.5.** `grep -rn
      "refresh_ui_bundle\|ui-check\|make ui" .github/workflows/` returns **nothing** — no workflow
      runs `make ui`, `make ui-check` or any drive script. Both fixes are guarded only by a developer
      running them by hand. Do not add a CI job for it in this change (out of scope), but say so in
      the commit message, and prefer `os.environ.setdefault` in 3.1/3.5 precisely because it cannot
      break a caller that *does* set `DATABASE_URL`.

## Group 4 — (d) and the prose that carried the guarantee

- [ ] 4.1 `hub/hub/config.py:10-15`: rewrite `_default_database_url()`'s docstring. The current text
      says the default is *"Only consulted by callers that skip the CLI"* and *"this default never
      fires there"* — the second clause is false and the first describes the dangerous path as safe.
      Say instead what the function now is: quoted by the refusal, never used as a fallback, and the
      path bare `agentweave` resolves to **on the default profile when the environment carries no
      `DATABASE_URL` of its own**. **(R4)** That qualification is not decoration.
      `_hub_resolve_database_source` (`src/agentweave/cli.py:617-621`) hands a pre-existing
      `DATABASE_URL` through unchanged, and `--profile` computes a different path. An unqualified "the
      path bare `agentweave` resolves to" repeats the defect (d) exists to remove: a docstring stating
      a guarantee the code does not keep.
- [ ] 4.2 **(R3 guard on every task in this group.)** Nothing rewritten here may assert the working
      directory the 2026-09-19 start ran from. The finding does not establish one, and the two
      candidates give different databases (from `hub/`, `hub/.env` resolves to `hub/data/`; elsewhere
      the home default). Describe the *failure mode* — a `DATABASE_URL` that did not reach the
      process — not a reconstructed location. See R3's note in `design.md`.
      Then: `.claude/handoffs/DEAD-ENDS.md`, § *Starting a Hub from source can land on the operator's
      real database*: correct the sentence *"`sqlite3`/`aiosqlite` will not create a missing parent
      directory … making directory-existence the cheap thing to check first."* True of raw
      `aiosqlite` (measured: `OperationalError: unable to open database file`), **false of the Hub**,
      which calls `os.makedirs(..., exist_ok=True)` at `engine.py:346-350`. **Keep the check and
      strengthen it:** because the Hub would have created the directory, a profile directory that does
      not exist afterwards proves the URL never reached the process at all. Add the date and the
      change name.
- [ ] 4.3 Same entry: replace *"verify from the server's own startup log — a fresh throwaway file
      logs the whole `0065→0103` migration chain, an existing database logs only `Application startup
      complete`"* with group 2's line, which states the fact instead of requiring it to be inferred
      from an absence. **Keep the migration-chain tell as a fallback for Hubs older than this change**,
      labelled as such.
- [ ] 4.4 Same entry: state the recovery as *kill the PID group 2's line printed; failing that,
      `netstat -ano` for the `LISTENING` PID on the port* — and keep the standing warning that
      `taskkill /IM python.exe` does not match `pythonw.exe`, so the operator's app can be killed by it
      while `Get-Process` shows no `python`.
- [ ] 4.5 `.claude/reference/hubs.md`: the runbook currently hands an agent a `DATABASE_URL=… py -3.11
      -m uvicorn …` line (`:28`) and nothing that catches the case where the variable does not arrive.
      Add one sentence saying the Hub now refuses rather than falling back, and that the startup line
      names the file — so the procedure is "read the line", not "infer from what is missing".
      **(R4) Also correct `hubs.md:36-38`, which is false.** It says `:8000` is
      `Python311\pythonw.exe -m uvicorn hub.main:app --port 8000`, and read that way this change would
      brick the operator's app on its next restart. Measured read-only on 2026-09-21:
      - The desktop shortcut `C:\Users\huida\Desktop\AgentWeave.lnk` targets `pythonw.exe -m
        agentweave`, with cwd `C:\Users\huida`.
      - That CLI sets `DATABASE_URL` (`cli.py:1038`) and spawns `[sys.executable, "-m", "uvicorn",
        "hub.main:app", "--host", "127.0.0.1", "--port", "8000"]` with `env=os.environ.copy()`
        (`cli.py:1066-1093`).
      - PID 9940's command line is exactly that spawn. `hub.pid` holds `9940` / `8000`, written at
        `cli.py:1108`.
      - `_hub_load_env_into` only `setdefault`s, so `~/.agentweave/hub/.env` cannot displace the
        variable.
      So `:8000` is a **told** launch, and (a) does not refuse it. Replace the sentence with that chain,
      and add what it implies for (b): the detached child's `stdout`/`stderr` are `DEVNULL`
      (`cli.py:1096-1097`), so on `:8000` group 2's line is emitted and **read by no one**. That is a
      known limit of this change, not a defect in it, since F388's launch was a direct one.
- [ ] 4.6 `CLAUDE.md`, § *The Hubs on this machine*: the prose *"never `agentweave --port 8010`"* and
      *"confirm which database a running instance serves before trusting it"* now has a mechanism
      behind it. Add at most **one sentence** — this file is re-read on every request of every session
      and its size is a standing constraint.
- [ ] 4.7 **(rewritten by R2 — R1's version of this task would have broken Docker.)**
      `hub/.env.example:5` ships `DATABASE_URL=sqlite+aiosqlite:///data/agentweave.db`. **Do not make
      it absolute.** That file is the *container's* template and the relative value is correct there:
      `hub/Dockerfile:11` sets `WORKDIR /app`, `hub/docker-compose.yml:23` mounts the `hub-data`
      volume at `/app/data`, the file's own line 4 says *"inside the container"*, and
      `docker-compose.yml:31-34` supplies the same value under `environment:` (which overrides
      `env_file:`) so line 5 is inert in the documented install anyway. **Instead, add two comment
      lines** saying that this value is the container path, and that a **source checkout** copying
      this file to `hub/.env` must replace it with an absolute path — because a `.env` satisfies the
      refusal (D3) while still being cwd-relative, which is the one way the launch-directory
      dependence survives (a). Do **not** touch `hub/.env` itself; it is gitignored local state.
- [ ] 4.8 Do **not** change `hub/docker-compose.yml:34`. Its relative `data/agentweave.db` is
      container-internal and paired with a named volume; it is a told path and it is correct.
- [ ] 4.10 **(R4)** `hub/tests/test_config.py:1-7`, the **module** docstring. It restates the
      guarantee (a) removes: *"a caller that skips the CLI (direct `uvicorn hub.main:app`, or any future
      embedder) lands on the same database regardless of its launch directory."* Task 1.9 fixes a
      different docstring in the same file (`:56-58`), and 4.1 fixes `config.py`, so without this task
      the change deletes the false sentence in one place and leaves a live copy beside the tests that
      now assert its opposite. Rewrite it to say what the file now guards: the refusal, the told
      paths, and the CLI/Hub path seam (1.7).
- [ ] 4.11 **(R4)** `docs/getting-started/installation.md:52-62`, § *If you've been running the Hub
      directly*. **This is user-facing and ships to GitHub Pages.** It tells a reader that for
      `uvicorn hub.main:app` run directly, the directory-relative resolution *"is fixed going
      forward"*, meaning a direct launch lands on the shared home database. After (a), a direct launch
      with no `DATABASE_URL` refuses instead. Rewrite the paragraph to say three things:
      - a direct launch must name its database with `DATABASE_URL`;
      - it refuses when it does not, and the message names the path;
      - bare `agentweave` is how to get the shared default.
      Keep the existing note that nothing migrates data automatically. No round before R4 swept
      `docs/`.
- [ ] 4.9 **(R2)** `tests/test_hub_commands.py`, the **CLI** suite — not `hub/tests/`. The test
      `test_first_start_migrations_leave_a_database_that_can_hold_a_conversation` (`:700-735`) does a
      bare `import hub.config` at `:707` to find the package directory, with no `DATABASE_URL` set.
      Measured under R2's probe: it fails, and its own
      `with patch.object(settings, "database_url", db_url)` cannot save it, because the module-level
      `Settings()` has already raised during the import. Set `DATABASE_URL` (the test already builds
      `db_url` from `tmp_path`) via `monkeypatch.setenv` **before** the import, or import
      `hub.config` behind the same guard. Do not weaken what the test asserts — it is F329's only
      regression guard at the CLI boundary. Then run `py -3.11 -m pytest tests/ -q` and record the
      count: under the probe it was `3 failed, 532 passed, 3 skipped`, of which **two failures are
      pre-existing `test_skill_sync.py` ones unrelated to this change** (confirmed on a clean tree
      2026-09-20). Expect them; do not fix them here, and do not let them hide a third.

## Group 5 — the spec, and what it costs

- [ ] 5.1 Apply `specs/app-lifecycle/spec.md`'s `MODIFIED` requirement. **Note what it removes**: the
      scenario *"The Hub's own database is launch-directory-independent"*, which normatively required
      a no-`DATABASE_URL` `uvicorn hub.main:app` to resolve to the home path. That scenario **is**
      F388. Removing it is the point; saying so out loud is the task.
- [ ] 5.2 **(rewritten by R2.)** Check that the guarantee the removed scenario existed to protect is
      still carried. It is, by the new scenario *"The database a launch path names does not depend on
      its working directory"* — the real requirement (no cwd-relative paths) separated from the
      fallback that was doing the work. **R2 narrowed two scenarios that the code falsifies as R1
      wrote them; apply them as they now stand and check the narrowing rather than the claim:**
      (i) that scenario originally required *any* environment file shipped with the Hub to carry an
      absolute path, which is false of `hub/.env.example` and correctly so (task 4.7), so it is now
      scoped to launch paths that resolve a path **for the host**; (ii) *"A told database is named
      before it is opened"* originally required the statement to precede *"creating a directory,
      creating a file, or applying a migration"* for every told launch, which native `agentweave`
      (`src/agentweave/cli.py:1054`) and Docker (`hub/Dockerfile:31`) both falsify by migrating in a
      separate step before `lifespan()` ever runs, so it is now scoped to a direct
      `uvicorn hub.main:app` — the launch F388 happened on — with the other paths covered by a
      weaker "states it at startup" clause.
      **(R3 verdict: the narrowing is right, not convenient.)** R3 re-derived both from
      `hub/Dockerfile:31`, `hub/docker-compose.yml:23,34` and `src/agentweave/cli.py` *before*
      reading R2's version, and reached the same two conclusions independently. On (ii) R3 also found
      the sharper reason R2 did not have: `_hub_resolve_database_source` (`cli.py:599-616`) returns
      `message=None` for the **default** profile, so a plain `agentweave` start names the database
      **nowhere** before `_hub_run_migrations` (`:1054`) opens it — it prints a path only for a
      *named* `--profile`. The broad scenario was therefore not merely unproven on the native path,
      it was **unsatisfiable there without changing the CLI**, which is outside this change. Narrowing
      was the only honest option. Apply 5.2 as it stands.
      **(R3, third scenario.)** R3 also narrowed *"A container's own relative database path is not a
      host path"*. As R2 left it, its final clause required *the file* to state it is a container
      path, and it covered *"an environment file **or compose file**"* — but `docker-compose.yml:34`
      carries no such statement and **task 4.8 forbids changing it**, so the delta contradicted the
      tasks. The clause is now scoped to a file that is *a template intended to be copied*, which is
      `hub/.env.example` (task 4.7) and not the compose file. Check this pairing survives IMPL: if
      4.8 is ever reopened, the scenario moves with it.
- [ ] 5.3 `openspec validate a-hub-that-was-not-told-which-database-refuses-to-open-one --strict`
      passes. **Not evidence of anything but the file's shape** — record it, do not lean on it.
- [ ] 5.4 Run `py -3.11 -m pytest hub/tests/ -q` in full and **write the count into this file.** Not
      `test_config.py` alone: this change edits `main.py`'s `lifespan()`, which every API test starts.
      F392 was filed on 2026-09-20 for a task ticked on the strength of a run nobody recorded — do not
      add to it.
- [ ] 5.5 `ruff check src/ hub/ tests/` and `black --check --target-version py311 src/ hub/hub/
      hub/tests/ tests/` over exactly CI's paths.

## Group 6 — drive it, because a passing suite is not proof

- [ ] 6.1 The refusal, for real: from a directory with no `.env`, `DATABASE_URL` unset, run
      `py -3.11 -m uvicorn hub.main:app --port 8093`. It must fail to start and print 1.4's message.
      **Then confirm nothing was created** — no new file, no new directory at the default path. This
      is the one check that matters and no unit test can make it.
- [ ] 6.2 The startup line, for real: start the same command with `DATABASE_URL` naming a **new**
      throwaway profile and read the output. The line must appear (D5's whole claim is that an `INFO`
      one would not), must name the absolute path, and must say the file did **not** exist. Then stop
      it and start it again against the same file: the line must now say it **did**.
- [ ] 6.3 Kill it by the PID the line printed. If that does not stop the server, group 2's line is
      printing the wrong PID — which uvicorn's reload/spawn behaviour makes a live possibility, and
      `DEAD-ENDS.md` already records that the launching shell's PID is not the listening one.
- [ ] 6.4 **Never against port 8000, 8010, `~/.agentweave/hub/data/`, `proj-5e960453` or
      `proj-18e5d4e0`.** Use a port in the 8090s and a profile directory created for this drive and
      deleted after.
- [ ] 6.5 Write the drive up in `scripts/drive/FINDINGS.md` as a `D-n` narrative entry, and set
      `**Status:** fixed <sha>` on **F388** only once 6.1, 6.2 and 6.3 have all been observed — not
      when the suite goes green.
