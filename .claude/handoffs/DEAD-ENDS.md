# Dead ends — the durable ledger

Things that do not work on this machine, in this repository, or with these tools, and the symptom
you will see when you hit one. **Append-only.** An entry is never deleted; when it stops being
true it is marked `RESOLVED` with the date and what changed, because "we used to believe this"
is itself worth knowing.

## Why this file exists

Until 2026-09-04 these facts lived only in each handoff's `## Dead ends` section, carried forward
by whichever session happened to write the next handoff. That made survival a coin flip, and the
cost was measured across the 108-handoff chain:

| Fact | Appears in handoff |
|---|---|
| Bash-tool `cd` persists between calls | 0003, 0020, 0024–0027, 0055, 0059, 0068, 0081, 0095–0098, 0106 — **then dropped** |
| `openspec --strict` reads only the first physical line | 0042–0046, **46-handoff gap**, 0093, 0096–0108 |
| `git merge -F -` does not read stdin | 0064, **40-handoff gap**, 0105–0108 |
| `pytest --timeout=` unavailable in `hub/tests/` | 0044, 0052, 0068, 0081, 0087–0088, gap, 0102–0108 |

Every one of those was paid for more than once. The `cd` entry was written down at handoff 0003,
re-learned at least seven times, dropped before 0107 — and cost three failed tool calls on
2026-09-04, during the session that built this file.

Compiled from 1,387 dead-end bullets across 193 handoffs (1,241 unique after dedupe). The same
fact recurred in up to five different phrasings — `npm run lint does not work` alone appears 19
times across 4 wordings. What follows is the deduped set, with the canonical phrasing.

## How to use it

- `/resume` reads this file. `/handoff` appends to it rather than re-copying the list forward.
- **Verify before trusting an entry older than a few weeks.** Entries carry the date they were
  last confirmed. Two facts in the founding set were already false when this file was compiled —
  see `RESOLVED` below — and an inherited-but-stale entry is worse than no entry, because it is
  believed.
- Add an entry the moment something costs you a second attempt. One line, the symptom, the date.

---

## Shell — the Bash tool

- **`cd` persists between calls.** A later call inherits the previous call's working directory.
  A background `pytest hub/tests/` once inherited a `hub/ui` cwd, collected nothing, and
  **exited 0** with "no tests ran". Use absolute paths after any `cd`, and never trust a
  background run's exit code alone — read the tail. *(Confirmed 2026-09-04, three times.)*
- **Long heredocs mangle content.** A ~180-line `cat > file <<'EOF'` through the Bash tool fails.
  Backticks, apostrophes inside Python string literals, and `\n` escapes are all eaten. Use the
  Write/Edit tools for anything longer than a few lines, and `git commit -F <file>` for commit
  messages. *(Confirmed 2026-09-04 — this file was written with Write for exactly this reason.)*
- **Backticks in a double-quoted commit message execute.** `git commit -m "... `foo` ..."` runs
  `foo`. Use `git commit -F <file>`.
- **`git merge -F -` does not read stdin.** Write the message to a file first.
- **`grep -c` returning 0 exits 1**, which kills a `&&` chain. Use `;` or `|| true`.
- **`grep -oE` truncates at the em-dash** in files that use them as separators (`FINDINGS.md`
  headings).
- **A foreground `sleep` is blocked** by the harness, chained before or after another command.
- **A background shell dies at session teardown.** Anything that must outlive the session needs
  WMI (`Invoke-CimMethod Win32_Process Create`), not a backgrounded Bash job.
- **The Bash tool caps at 600s.** `pytest hub/tests/` exceeds it — see below.
- **A piped run reports the last command's exit code.** Use `${PIPESTATUS[0]}` when piping through
  `tail`.
- **`strings` is not available** in this Git Bash. Use `grep -ao`.
- **`grep -rn ... hub/` times out** — it walks `hub/ui/node_modules`. Scope the path or use the
  Grep tool.

## Python and interpreters

- **Use `py -3.11`, never bare `python`.** `python` resolves to
  `~/AppData/Local/hermes/hermes-agent/venv/Scripts/python` — a different environment that yields
  3 phantom `pty_runner` failures on a tree that is actually green. *(Confirmed 2026-09-04.)*
- **`python` now *has* pytest (9.1.1), which makes this worse, not better.** The old entry read
  "the default python on PATH has no pytest" — it fails loudly no more. It runs, and lies.
  *(Updated 2026-09-04.)*
- **Only Python 3.11 exists on this machine**; 3.12 is CI-only. `black` therefore needs
  `--target-version py311` or it refuses with a safety-check warning.
- **`py -3.11 -c` printing `→` or `—` dies with `UnicodeEncodeError`** — stdout is cp1252. Set
  `PYTHONIOENCODING=utf-8` or avoid the characters.
- **`py -3.11` cannot open a Git Bash `/tmp/...` path.** Use a Windows path.
- **`py -3.11 -c "import hub.main"` from the repo root fails** with an ImportError — this repo's
  `hub/` directory shadows the installed `hub` package. See the Hub section.
- **`shutil.rmtree(..., ignore_errors=True)` is a lie on Windows** — it silently leaves the tree.
- **`sqlite3` is not on PATH.** Use `py -3.11 -c "import sqlite3; ..."`. *(Confirmed 2026-09-04.)*
- **`ruff` and `mypy` are not on PATH in Git Bash.** Use `py -3.11 -m ruff`, `py -3.11 -m mypy`.
  *(Confirmed 2026-09-04.)* **And the failure is silent, which is why this entry keeps being
  re-learned** *(2026-09-09)*: `ruff check src/ hub/ tests/ 2>&1 | tail -5` prints
  `command not found` and then reports **exit 0**, because `$?` is the pipeline's last stage. A
  lint gate written that way reads as a pass while nothing ran. `black` *is* on PATH, so two of
  the three commands in the documented gate work and only the other two lie.
- **`pip` warns about two invalid distributions** in Python311 site-packages (`~gentweave-ai`,
  `~nteragent-framework`) — leftover partial uninstalls. Harmless noise, not a failure.
  *(Observed 2026-09-04.)*
- **The global Python resolves `import hub` to THIS CHECKOUT from any directory**, not only from the
  repo root — `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\__init__.py`, confirmed with cwd
  set to `C:\Users\huida`. The repo-root shadowing entry above understates it. Consequence, found
  live: a `python -m uvicorn hub.main:app` started by the *global* interpreter serves the
  development checkout's code, whatever database it is pointed at. *(Confirmed 2026-09-07.)*
- **A Windows venv `python.exe` re-execs the base interpreter, so process listings name the WRONG
  interpreter.** `Get-CimInstance Win32_Process` reported
  `AppData\Local\Programs\Python\Python311\python.exe` for a server actually launched from
  `agentweave-live\venv\Scripts\python.exe`; `sys.executable` inside the process correctly reported
  the venv. Do not conclude "the wrong Python is running" from a command line alone. Check the
  **parent** process, or `(Get-Process -Id N).Modules` for paths under the venv. *(Confirmed
  2026-09-07, cost one false diagnosis.)*

## pytest

- **`pytest --timeout=` does not work in `hub/tests/`** — `pytest-timeout` is not installed;
  collection fails with exit 4. Use an external timeout. *(Confirmed 2026-09-04.)*
- **`pytest hub/tests/ tests/` in one invocation fails collection.** Both trees contain a
  `test_mcp_server.py`. Run them separately.
- **The Hub suite takes 20–24 minutes** and exceeds the Bash tool's 600s cap. Run it in the
  background or in chunks, and do not poll it.
- **`pytest -q` buffers everything**, so a redirected background run's file lags reality badly.
  A `[ NN%]` marker read from that file is meaningless — measure elapsed time from the process
  (`Get-Process | StartTime`) instead.
- **`pytest <nonexistent_file.py>` runs nothing and reports success-shaped output.** Check the
  collected count, not just the exit code.

## git

- **`git worktree add` into the scratchpad fails** with "Filename too long".
- **Stage explicit paths.** `git add -A` sweeps in scratch files.
- **CI triggers only on push to `master` and PRs to it.** ~~A feature branch push runs
  nothing.~~ **RESOLVED 2026-09-06 — false as of the merge-gate work.** `ci.yml` now builds
  `autonomous/**` too (a prerequisite for the day window's merge gate, landed circa
  2026-09-04). Confirmed directly: every push to `autonomous/2026-09-04-daily` this session
  (six of them) triggered its own CI run, checkable with
  `gh run list --branch <branch> --limit N --json headSha,conclusion,status,databaseId`.
- **`gh run view --log` and the REST job-logs endpoint both refuse a still-running job.**
  `gh run view <id> --log` prints `run <id> is still in progress; logs will be available when
  it is complete` (exit 0, no content); `gh api repos/<o>/<r>/actions/jobs/<jobid>/logs`
  404s with `BlobNotFound`. There is no CLI-accessible live tail. The only thing you can read
  from an in-progress run is job/step *status* and timestamps —
  `gh run view <id> --json jobs --jq '.jobs[]|{name,status,conclusion}'`, or per-step
  `startedAt`/`completedAt` — which is enough to notice a job has been running far longer
  than its historical ceiling, just not to see why. *(Hit 2026-09-06, diagnosing a 3.5-hour
  `hub-test` hang — F292/F295.)*
- **A backgrounded `gh run watch <id> --exit-status` loses its exit code if anything is
  chained after it.** `Bash({..., run_in_background: true})` reports the exit code of the
  **last command in the string**, not of `gh run watch` specifically — `gh run watch $ID
  --exit-status; echo "DONE=$?"` always notifies "exit code 0" because `echo` always
  succeeds, even when the run actually failed. This is the `run_in_background`/task-
  notification-specific case of the general piping trap two entries up; it cost a session a
  wrong "CI is green" report to the operator on 2026-09-06 (the run had actually failed on an
  unrelated lint error). Run `gh run watch ... --exit-status` **alone**, as the entire
  backgrounded command, so the notification's exit code is the real one.
- **A `.gitignore` entry ending in `/` cannot be un-ignored by a later `!` negation.** Git does
  not descend into an excluded *directory*, so the negation is unreachable and the file stays
  ignored with no error. Exclude the contents instead — `dir/*` plus `!dir/keepme` — which
  leaves the directory itself visible. *(Hit 2026-09-04 adding `.claude/handoffs/*` with an
  exception for `DEAD-ENDS.md`.)*
- **`git check-ignore -v` cannot answer "is this ignored?" when a negation matches.** It prints
  the matching rule — including a `!` rule — and its exit code does not distinguish "ignored"
  from "explicitly un-ignored", so the obvious `&& echo ignored || echo not` test reports the
  opposite of the truth. Verify with `git add <path>` (does it get staged?) or
  `git status --short --untracked-files=all`. *(Hit 2026-09-04.)*
- **A commit made while an unattended window owns the tree must stage explicit paths and land
  immediately.** The window's agent is instructed to "never end an iteration with a dirty
  tree" (`.claude/skills/autonomous-session/scripts/run-iteration.ps1:196`), so any stray
  modified file left sitting will be swept into *its* commit. *(2026-09-04.)*
- **`git branch -d` refuses a branch that IS merged to master when its remote-tracking ref has
  diverged.** The message says so explicitly — "not deleting branch X that is not yet merged to
  `refs/remotes/origin/X`, **even though it is merged to HEAD**" — and is easy to misread as "this
  branch has unmerged work". Before reaching for `-D`, check the remote side directly:
  `git rev-list --count master..origin/<branch>`. Two branches reported this on 2026-09-07 and both
  returned **0**, i.e. nothing was at risk. *(Confirmed 2026-09-07.)*
- **`git worktree remove` needs the worktree's own path, and the branch stays behind.** Removing the
  directory does not delete the branch; run `git worktree prune` afterwards, then delete branches
  separately. Seven worktrees were removed this way on 2026-09-07 (six `agentweave/*` roster
  leftovers under `.agentweave/worktrees/`, plus the sidequest worktree). *(2026-09-07.)*

## openspec

- **`openspec` is on PATH directly** — `npx` is no longer required. *(Updated 2026-09-04; earlier
  entries all said `npx openspec`.)*
- **`openspec validate --strict` reads only a requirement's FIRST PHYSICAL LINE** when looking for
  `SHALL`/`MUST`. A requirement whose keyword is on line 2 is invalid and the message does not say
  why.
- **`openspec` rejects change names starting with a digit**, including date-prefixed ones
  (`2026-08-07-foo`) — and `status --change` rejects them too, not just `new`.
- **`openspec validate` with no target exits "Nothing to validate"** rather than failing. Pass
  `--all --strict` or a named change.
- **There is no `openspec sync` command** — the skill applies deltas by hand.
- **`openspec archive` prefixes the archive directory with the *UTC* date** when the change name
  does not already start with it, so a change archived after local midnight but before UTC midnight
  gets a **double date**. *(2026-09-10.)* `2026-09-07-clearing-instructions-asks-first` archived at
  00:59 local / 23:59 UTC and landed as
  `openspec/changes/archive/2026-09-09-2026-09-07-clearing-instructions-asks-first`. Left as the tool
  produced it — renaming by hand makes the result unreproducible — but do not read the leading date as
  the day the work was done.
- **`openspec archive` updates main specs by default; `--skip-specs` is how a hand-merged sync
  survives it.** *(2026-09-10.)* The bare command advertises "archive a completed change **and update
  main specs**", which would put a mechanical update on top of a file whose value is the judgement
  hand-merged into it. `--skip-specs` and `--no-validate` are **separate** flags, so skipping the spec
  step still validates. Verified by `md5sum` either side of the archive: byte-identical.
- **Clearing `testbed/` deletes evidence that live openspec changes cite.** *(2026-09-08.)* The
  2026-09-07 clean slate emptied `testbed/` to its two tracked files; the still-unapproved change
  `2026-09-07-a-dead-connection-is-never-handed-back-out` cites
  `testbed/scratch/f295/probe_pool.py` in `tasks.md:16` as the measurement that established which
  attributes its guard reads. The probe is gone and the citation is dead. **Before clearing the
  testbed, grep `openspec/changes/` for `testbed/`** — or accept that a proposal's evidence becomes
  unreproducible. (The specific probe was re-derived on 2026-09-08; see the SQLAlchemy section.)

## Node and the Hub UI

- **`cd hub/ui` first.** `npx vitest` from the repo root resolves a different project and picks up
  the wrong config.
- **`scripts/refresh_ui_bundle.py` must be run from the repo root**, not from `hub/`.
- **`cp -r dist/ static/ui/` merges rather than replaces.** Use the script, which is what records
  `ui-build-stamp.json`.
- **`npm test -- --runInBand` is invalid for Vitest.** Use `npm test`.
- **vitest full-suite runs flake on `chartersUi` / `runnersUi`** under a 5s timeout.
- **Adding a hook to a component breaks every test that mocks that component's module.** Nine UI
  test files mock `@/api/questions`; seven mock `@/api/permissions`.

## The Hub at runtime

- **`agentweave --port 8010` cannot start the trial Hub.** The console script is the *installed*
  `agentweave-hub`, whose bundled migrations lag this checkout — it dies with
  `Migration failed: Can't locate revision identified by '00NN'`. Start from `hub/` with uvicorn
  from source. This cost two sessions on 2026-08-24.
- **The Hub cannot be started from this repo's root.** `-m` puts the cwd on `sys.path[0]`, so this
  repo's `hub/` shadows the installed `hub` package and the child dies with
  `ImportError: cannot import name '__version__' from 'hub'` — 60 seconds later, with its output
  already sent to `DEVNULL`. Start from `hub/`.
- **The Hub API rejects `X-API-Key`.** Use `Authorization: Bearer <key>`.
- **A Hub restarted onto a stale database still answers `{"status": "ok"}`.** Health is not a
  database-identity check — confirm which file it serves by hitting the API and comparing mtimes.
- **Static UI changes appear without a restart; Python changes do not.**
- **Restarting the Hub: kill by exact PID and verify the new process**, then re-check. Stale PID
  files (`hub-8010.pid`, `hub.pid`) outlive their processes.
- **`PowerShell`'s `Invoke-RestMethod` swallows error bodies.** Use `curl`.
- **Deleting a Hub database orphans every `.agentweave/project.json` marker that pointed into it,
  and the installed 1.1.0 then refuses those directories.** Adding such a directory fails with
  `project_identity_conflict` — *"marked directory is a copied or orphaned project identity;
  register the copy explicitly as new"*. The error is about a **file on disk**, not about database
  rows, so "I reset the database" does not fix it: delete the stale `project.json` (keep the
  `logs/`, `context/`, `worktrees/` beside it) and the directory registers fresh. Seven orphans
  were left across this machine on 2026-09-07 by exactly this route. **Fixed on master** by
  `8ac12db` ("Adopt an orphaned project marker instead of refusing it") plus `fd3fea4`, which
  recreate the project reusing the marker's id and persist a `project_adopted` event — so this trap
  is specific to builds at or before PyPI 1.1.0. *(Confirmed 2026-09-07.)*

## SQLAlchemy and Hub test patterns

- **`async with engine.begin()` does NOT put DDL in a transaction on SQLite** *(measured
  2026-09-10, and five F292 windows had assumed the opposite)*. SQLAlchemy's pysqlite/aiosqlite
  dialect emits no `BEGIN` until a **DML** statement, and `DROP TABLE`/`CREATE TABLE` are DDL. So
  `driver_connection.in_transaction` reads **`False`** after the first `DROP` inside the block, no
  `BEGIN` ever reaches the driver, and each of the ~90 drops in `Base.metadata.drop_all` is its own
  autocommit write transaction — taking and releasing SQLite's write lock ninety times, with a
  window between each for any other connection to take it. **Do not reason about "the transaction"
  around a `drop_all`; there isn't one.** If you need the sequence to be atomic, issue
  `await connection.exec_driver_sql("BEGIN IMMEDIATE")` first, which is what `hub/tests/conftest.py`
  now does. Verify with `in_transaction`, not by reading the `async with`.
- **`database is locked` has two mechanisms and only elapsed time tells them apart** *(measured
  2026-09-10)*. A genuine holder makes you wait out `busy_timeout` and then fail. But in WAL, a
  connection that took a read snapshot and then asks to upgrade to a write is refused
  **immediately, `busy_timeout` ignored, with nothing holding the file** — SQLite returns
  `SQLITE_BUSY` rather than risk deadlock. Measured side by side: **0.000 s** (snapshot, 30 s
  timeout ignored) vs **2.234 s** (real holder, 2 s timeout honoured). **Before hunting for a
  holder, record how long the failing statement waited** — sub-second means there may be no holder
  to find, and every instrument that samples for one will come back empty and look broken.
- **`session.get(Conversation, "conv-…")` silently never matches** — the primary key is not what
  you think it is. Query explicitly.
- **`session.delete()` refuses a never-flushed object.**
- **`ORDER BY EventLog.id` does not order by recency.** Order by timestamp.
- **`extra: "forbid"` rejects a forbidden *key* regardless of its value** — including `None`.
- **There is no `db_session` fixture.** Use `async_session_factory()` from `hub.db.engine`.
- **The `app` fixture is an httpx client with no `.routes`.**
- **Never read `create_app().routes` directly — this machine's Starlette is two majors behind CI's,
  so the shape you measure locally is not the shape CI sees.** *(Measured 2026-09-09.)* Here:
  starlette **0.52.1** / fastapi **0.136.3**. CI resolves starlette **1.6.0** / fastapi **0.141.1**
  fresh on every run (read off run `34325989834`'s install step), and 1.x stopped flattening
  `include_router` into `app.routes`: it holds `_IncludedRouter` wrappers whose inner `APIRoute`s
  carry *relative* paths. A direct comprehension therefore sees only the routes declared on the app
  itself — `/health`, `/docs`, `/assets`, `/openapi.json` — and every `/api/v1/...` path looks
  absent. **Use `api_route_paths` / `iter_api_routes` from `hub/tests/_routing.py`**, which walks
  either shape. This has now been the same mistake three times (`test_mcp_body_contract`,
  `test_request_strictness`, and `test_mcp_adapter_online`); the third cost **twelve consecutive red
  `hub-test` runs** and held the daily loop's merge gate shut for two days, as the only failure in
  4,032 tests, while passing locally every time it was run.
  **To check a framework-shape assumption against CI without waiting for CI**, build a throwaway
  venv — `py -3.11 -m venv <tmp>`, then `pip install -e ./hub[dev]` and `pip install -e .` into it,
  which resolves the newest allowed starlette exactly as CI does (~4 min). Run the suspect file
  with that interpreter. This is the only local way to see the 1.x route shape; the repo venv
  cannot show it.
- **`run.task_id` is NULL on most runs** — 154 of 202 measured. Read the transition table instead.
- **`run_job` returns 503 in tests** unless `get_scheduler()` is patched.
- **The aiosqlite connection internals the F295 guard reads ARE reachable from a pool listener,
  and the `close` pool event does fire.** *(Re-derived 2026-09-08 against SQLAlchemy 2.0.50 /
  aiosqlite 0.22.1, replacing the deleted `testbed/scratch/f295/probe_pool.py`.)* From a
  `checkout` or `close` listener on `engine.sync_engine`:
  `dbapi_connection` is `AsyncAdapt_aiosqlite_connection` → `._connection` is `aiosqlite.Connection`
  → `._thread` is a `Thread` with a working `.is_alive()`, and `._running` is present. Use
  `getattr(..., None)` for each — the guard is written to no-op when the shape is absent rather
  than crash a healthy checkout.
- **aiosqlite's own guards are two lines later than the change documents cite.** *(2026-09-08,
  aiosqlite 0.22.1.)* `close()`'s `if self._connection is None: return` is at `core.py:202-203`
  (cited as `199-201`, which is the `def` and docstring); `_execute`'s
  `raise ValueError("Connection closed")` is at `core.py:152-153` (cited as `151-152`) and its
  predicate is `not self._running or not self._connection` — **two** conditions, not one. The
  mechanism and the exception text in the citations are right; only the line numbers drift.
- **A payload-shaped model function must be tested against real route ordering.** A fixture in an
  order the route never emits is not evidence (F190: ascending lifecycle events fed to a route
  that returns newest-first, green for a month while the behaviour could not fire).

## Browser and preview tooling

- **`preview_snapshot` returns ~25k tokens.** Use `preview_evaluate` with a targeted expression;
  reserve snapshots for actual visual checks.
- **`preview_evaluate` must return an object**, not a bare array or null, or it fails MCP schema
  validation. Wrap: `(() => ({...}))()`.
- **Radix menu items need dispatched `pointerdown`/`mousedown`/`mouseup`** before `click()`.
- **`requestAnimationFrame` never fires and `ResizeObserver` never delivers** in this environment.
- **`setPointerCapture` is unimplemented in jsdom** and throws.
- **`ta.blur()` does not fire React's `onBlur`** under browser automation.
- **`scripts/uishot.py` cannot capture an authenticated page** — it has no session.
- **`page.goto(..., wait_until="networkidle")` never settles** against the Hub (SSE keeps the
  connection open).

## PowerShell (when driving it from the Bash tool)

- **`@'…'@` here-strings are PowerShell syntax and the Bash tool is Git Bash** — they do not work
  there, and mangle commit messages when attempted. *What it looks like, measured 2026-09-05
  (`6b98bdc`):* `git commit -m @'…'@` succeeds silently and produces a commit whose **subject line
  is a bare `@`**, with the real subject demoted to line 2 and a trailing `@` after the trailer.
  `git log --oneline` then shows `@` where the summary should be. It is not repairable after a
  push under a no-force-push rule, so the cost is permanent — use a Bash heredoc (`-m "$(cat
  <<'EOF' … EOF
  )"`) or repeated `-m` flags.
- **Bash-style quote escaping breaks PowerShell here-strings.** Keep each shell's syntax in its
  own tool.
- **`[System.Security.Cryptography.RandomNumberGenerator]::Fill()` does not exist on Windows
  PowerShell 5.1, and the failure is silent in the way that matters.** The method throws
  `MethodNotFound`, but if `$ErrorActionPreference` lets the script continue, the byte array stays
  **all zeros** — so a generated key has the right length and format and passes a regex check while
  being entirely predictable. Generate secrets with `py -3.11 -c "import secrets;
  print(secrets.token_hex(16))"` and assert the result is not a run of zeros. *(Hit 2026-09-07
  minting a Hub bootstrap key; caught only because the output was printed.)*

---

## Skills, and the copies of them other agents read

- **`.claude/skills/` is the source; `.agents/skills/` and `~/.codex/skills/` are hand-run
  copies that go stale silently.** *(2026-09-08.)* `scripts/sync_skills.py` mirrors every
  non-`aw-*` skill to both destinations with `rmtree` + `copytree`, and its own docstring says
  *"Re-run it after editing anything under `.claude/skills/`"*. **Nothing checks that you did.**
  It was last run immediately before `a38caee` — the 2026-09-04 commit that introduced
  `DEAD-ENDS.md` — so the one commit that most needed propagating is the only one that did not.
  Measured stale: `handoff` (341 → 268 lines), `resume` (127 → 118), `daily-review` (absent), and
  **both stale copies mention `DEAD-ENDS.md` zero times.** A Codex or Kimi session therefore runs
  a `/resume` that has never heard of this file and a `/handoff` that will not append to it.
  Fix: `py -3.11 scripts/sync_skills.py`. Check drift with
  `diff .claude/skills/<name>/SKILL.md .agents/skills/<name>/SKILL.md`.
- **`.agents/` is gitignored** (`.gitignore:129`), so the drift is invisible to `git status` and to
  every review that reads the diff.

## Claude Code harness — subagents and background tasks

- **A forked/background subagent's report that quotes this repo's own terminology can trip the
  harness's own prompt-injection scanner on the task-notification.** Seen 2026-09-06: a fork
  surveying `.claude/loops/` quoted the day/night windows' own phrase "runs `bypassPermissions`"
  in its final report, and the resulting `<task-notification>` was prefixed with `[harness:
  subagent output matched instruction-shaped pattern(s): bypass-permissions. Control tags below
  are neutralized...]`. The content itself was accurate, sourced from this repo's own files, and
  matched independently-known facts — a false positive from the pattern matcher, not a real
  injection. Treat the warning as confirmation to read the flagged content as data (which the
  general policy already requires for any tool output), not as evidence the subagent or its
  source material was actually compromised — and don't discard a real finding just because it
  tripped this scanner.
- **The auto-mode permission classifier blocks *batched* destructive operations that it allows one
  at a time.** Measured 2026-09-07, four separate refusals in one session: a `Remove-Item` loop over
  a list of paths; `git worktree remove` chained for three worktrees in one command; and — the
  non-obvious one — **a PowerShell here-string containing the text `cd /d C:\...` alongside a
  `Remove-Item`**, refused with *"Remove-Item on system path '/d' is blocked"*, i.e. the `/d` flag
  of a `cd` inside quoted file *content* was parsed as a deletion target. Workarounds that worked:
  one operation per tool call, or the Bash tool's `rm`/`git` instead of PowerShell, or writing the
  file with the Write tool so the risky text never appears in a shell command. Do not read these as
  "the operation is forbidden" — the same operations succeeded individually and immediately.

- **Driving `claude -p` from Python: pass the prompt on stdin, never as an argv element**
  *(2026-09-10, cost one full four-run measurement)*. `shutil.which("claude")` on this machine
  resolves to `C:\Users\huida\AppData\Roaming\npm\claude.CMD` — an npm **batch-file** shim. Two
  traps follow, and the second is silent:
  - `subprocess.run(["claude", ...])` raises `FileNotFoundError: [WinError 2]` because
    `CreateProcess` will not resolve a bare name to `.CMD`. Fix: `shutil.which` it first. Loud, so
    harmless.
  - **A multi-line prompt passed as an argument is truncated at its first newline**, because a
    batch file ends its line there. The run still succeeds, exit 0, valid JSON — and every model
    replied *"I don't see a command in your message."* Four runs, four plausible-looking results,
    all measuring nothing. **Read a result that says the model did not see your input as a
    delivery failure, not a model failure.** Fix: `subprocess.run([...], input=prompt)` with no
    positional prompt — `claude -p` reads stdin — which also sidesteps every quoting problem in a
    prompt full of `$`, quotes and backslashes.
- **`--dangerously-skip-permissions` is the discriminator between a *static* refusal and an
  *approval* refusal** *(2026-09-10)*. The harness's `permission_denials` records carry a
  `tool_name` and the `tool_input`, and **no reason field** — so "the command analyser rejected
  this shape" and "`acceptEdits` had nobody to answer" look identical, and the model's own
  narration about which one happened is unreliable prose. Re-run the same shape with the approval
  gate removed: what still fails is static, what now executes never was. This is what showed F301's
  five "refusal classes" to be reasons a command *needs approval* rather than reasons it is
  forbidden.

## The installed CLI (`agentweave` from PyPI, outside this repo)

Facts about driving a *real* AgentWeave instance, learned setting one up at
`C:\Users\huida\agentweave-live` on 2026-09-07. These are about the shipped product, not this
checkout — the dev-repo traps are in "The Hub at runtime" above and still apply there.

- **Every `agentweave` subcommand needs BOTH `--profile` and `--port` when the instance uses a
  named profile** *(measured 2026-09-07)*. Omit them and the CLI looks for the `default` profile,
  finds no native pid file, and **falls back to assuming Docker**. Two concrete consequences on a
  natively-started Hub: `agentweave status` prints `Status: running (docker)` — on a machine where
  the Docker daemon is not even running — and `agentweave stop` fails with
  `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`, stopping
  nothing and leaving the port bound. With the flags, both are correct (`running (native)` with a
  PID; stop kills the process pair and frees the port). **The failure mode is a misleading
  diagnostic**: it blames Docker when the real problem is a profile mismatch, which cost this
  session a nearly-filed false bug report. Wrapper at `C:\Users\huida\agentweave-live\hub.ps1`
  exists so the flags are never forgotten.
- **`agentweave doctor` lists runner CLIs it merely *detected on PATH*, not ones it can use**
  *(measured 2026-09-07)*. On this machine it reports `claude, codex, copilot, kimi, opencode` as
  an `[OK]` line. Only **claude** and **codex** can actually be bound to a Runner and spawned —
  `RUNNER_CLIS = ("claude","codex")` in `hub/hub/db/models.py:300`, and the spawn path 501s for
  anything else. Detection is not support, and nothing on the `doctor` output says so.
- **The pid the CLI reports at start is not the process holding the port** *(observed
  2026-09-07)*. Native start logs e.g. `Starting Hub (native, PID 17544)` and writes that pid to
  `~/.agentweave/hub/hub-<profile>-<port>.pid`, while a second python process (17208) is the one
  listening. `stop` handles this correctly and kills both — do not "fix" it by killing the
  recorded pid by hand.

## The `spec-queue/` contract — three ways a correct-looking document does nothing, or lies

- **A dated section's *premises* are not protected by the newest-section-only contract — only its
  *instruction* is** *(2026-09-08, found by the day window reconciling its own log)*. A
  `DIRECTION.md` or `ROADMAP.md` section is read as both an order and a description of the world,
  and the world moves under it. The 2026-09-08 `DIRECTION.md` section and `ROADMAP.md` were written
  by one DECIDE session at **00:30** and both assert *"not one carries an approval token"*;
  `0d82d6d` approved all four at **01:24**. The day window read them at **09:01**, 7 h 31 m later,
  and inherited the dead premise into eight iterations of its log without noticing — the queue was
  still right, but only because a second authority (the drain gate) reached the same shape by a
  route that did not depend on it. **Before quoting a dated section's arithmetic, check whether
  `APPROVALS.md` or the file it describes moved after that section's own timestamp**:
  `git log -1 --format='%ad' --date=iso -- spec-queue/APPROVALS.md` against the section's stated
  writing time. The same session's `ROADMAP.md` also contradicted itself, saying "starved of
  verdicts" in its headline and "all four APPROVED" twenty-five lines below — **a long plan file is
  read at whichever line the reader reaches first**, so a closure has to be written at the headline
  too, not only in the row it closes.
- **A verdict token under any but the *newest* dated section is never read** *(2026-09-08)*.
  `APPROVALS.md`'s own header says *"Newest day first. Days below the newest are history and are not
  read."* Three of the four changes approved on 2026-09-08 had their descriptive rows under
  `## 2026-09-07`, `## 2026-09-06` and `## 2026-09-05`; writing `APPROVED` in front of *those* rows
  would have looked entirely correct and been invisible to the FIX window. **Restate the row under
  today's heading** rather than editing a row in history. `DIRECTION.md` has the identical contract
  for the day window.
- **`APPROVED` alone does not get a change built — the default queue is backlog-first**
  *(2026-09-08)*. `spec-queue/README.md`, decided 2026-09-01: unarchived changes first, then open
  findings by severity, and `APPROVED` rows only **third**. Four freshly approved changes sit behind
  8 unarchived changes and the findings list unless an **`ORDER:`** line promotes them — and `ORDER`
  applies to **that night only**, so it needs rewriting every evening with whatever remains.
- **`<change-name>` in a row is the directory name under `openspec/changes/` exactly.** Cheap to
  verify (`test -d openspec/changes/<name>`) and worth doing, because a typo is a row the window
  silently cannot match.
- **Writing *tomorrow's* `DIRECTION.md` section before today's window has fired cancels today's**
  *(2026-09-08)*. Both files read **only the newest dated section**, and `day-window.md` step 5 then
  asks whether that section is dated **today** — so a `## 2026-09-09` heading added on 2026-09-08
  makes the `## 2026-09-08` section below it history, and the 08:55 window takes the *default* queue
  instead of the instruction sitting right there in the file. The symptom is a window that quietly
  does the ordinary thing on a day it was told not to. **Write the section on the morning it
  applies, or after that day's window has fired.** The same shape as the `APPROVALS.md` entry two
  bullets up, in the opposite direction: there, writing under an *older* heading is invisible; here,
  writing under a *newer* one is destructive.
- **A finding's banner saying "no drive exists" is a claim, not a fact — grep the finding's own
  number first** *(2026-09-08)*. The 2026-09-03 banners reopened four severity-A findings on the
  reasoning that an archived openspec change is *"a plan marked done, not a drive of the built
  product"*. Correct reasoning; wrong for **F140**, whose drive was already recorded in
  `FINDINGS.md` twelve thousand lines above, two days before the banner. It cost F140 five days and
  a place on the operator's blocked list. Searching `openspec/changes/archive/` is not the same
  search as searching `FINDINGS.md`. ~~**F154 and F155 still carry that banner and have not had this
  check.**~~ **Checked the same day, and both were the same error**: F154 fixed `001a07d` and driven
  18/18 by `t_f154_wedged_review.py`; F155 fixed `0373867` and driven 23/23 by
  `t_f155_conflict_remedy.py` — both on 2026-08-31, both recorded in `FINDINGS.md`, both banners
  written three days *after* the drive they said was missing. **Three of the four the banner reopened
  were already driven.** The severity-A count went six → five → three in one day with no product code
  written. This is no longer one anecdote about F140: the grep is a standing precondition for
  believing any "not driven" claim on this page, and it costs about ten seconds.

## Unattended runs — failure modes the driver does not detect

- **`STATE-night.json` and `STATE-day.json` are stale between runs by design — do not "repair" one
  before an arm** *(2026-09-08)*. Found `STATE-night.json` carrying `stop_at` three days in the past
  (`2026-09-07T07:00`), a `branch` that had been superseded, and a `parent_sha` far behind master.
  None of it matters: `.claude/loops/arm-cycle.ps1` **rewrites the file wholesale** at arm time —
  fresh `stop_at` (rolled forward a day if the window's `Until` has already passed), `iteration = 0`,
  `current = "compose"`, a new `log_file`, and a settled cycle branch with a current `parent_sha`.
  Editing the stale file by hand before 22:55 changes nothing and risks looking like state the
  window wrote.
- **`arm-cycle.ps1` refuses to arm on a dirty working tree** *(2026-09-08)*. It prints
  `REFUSING: working tree is dirty. Leaving this window unarmed.`, lists the paths, and **exits 3**.
  The Scheduled Task still reports success-ish and the window simply never runs. So uncommitted work
  left in the tree at 22:55 costs the entire night, silently, and the symptom appears only in
  `.claude/autonomous/driver-night.log`. **Leave the tree clean before an armed window's start
  time.**

- **A Claude usage limit turns an autonomous run into a silent no-op loop** *(measured
  2026-09-07)*. The headless CLI printed `You've hit your session limit · resets 7:10pm
  (Europe/Lisbon)` and exited 1. `run-iteration.ps1` logs the child's exit code and exits with it;
  **nothing counts consecutive failures**, so the Scheduled Task kept firing every 5 minutes and
  produced **24 consecutive 2–3 second no-op iterations over ~2 hours** before the limit reset.
  The task stays `Ready`, the state file never changes, and the driver log looks like a run that
  is simply between iterations. Its only self-stopping conditions are a null `next_action` and
  passing `StopAt`; neither covers "the child keeps failing". **Diagnose by comparing
  `iteration start`/`iteration end` timestamps — a healthy iteration takes minutes, a dead one
  takes seconds.**
- **A watcher must grep for the failure signatures, not only the success ones** *(learned the hard
  way, 2026-09-07)*. A background watcher armed for that run filtered on review-page mtime, task
  existence, and a guessed error alternation (`Stopping\.|did not parse|Refusing|not found`). A
  usage-limit death matched **none** of them, so it would have run its full five hours and
  reported "expired" after the run's own stop time — while the operator had been told progress
  would be reported. Silence read as success. Watch for **forward progress** (iteration counter or
  commit count advancing within a bound) rather than for the absence of known errors.
- **The morning merge gate is read at ~09:00 and will essentially always find CI mid-run**
  *(2026-09-08, found by the day window itself and confirmed here)*. `AgentWeaveArmDay` fires at
  08:55, the window composes and reads the gate within a few minutes, and the CI suite takes 15–25
  minutes — so the gate's *"CI concluded `success` for this exact commit"* condition is unmet at the
  only moment it is checked. It correctly refuses a stale green from an earlier commit, so the
  landing is deferred to a `gate-retry` item that may or may not get a firing. **A cycle that
  "never lands" is more likely this than a real gate failure** — check `gh run list --branch <cycle>`
  for a *later* success before diagnosing anything else.
- **CI red on `master` usually means `hub-test` alone, and usually means the F292 flake — not your
  change** *(measured 2026-09-08: 4 failures in the last 20 `ci.yml` runs, ~22%, worse than the
  "~1 in 6" previously recorded)*. Confirm before assuming a regression:
  `gh run view <id> --json jobs --jq '.jobs[] | "\(.conclusion)  \(.name)"'`. On 2026-09-08 two
  docs-only commits failed this way while the two around them passed. **The consequence that bites:
  a red `master` keeps the merge gate shut**, so an unrelated flake blocks the cycle from landing.

## Working in this checkout while an unattended window is running in it

*Added 2026-09-08. The day and night windows commit into the same working tree an interactive
session is sitting in, on a cycle branch, every few minutes.*

- **Check `git branch --show-current` before doing anything.** After `AgentWeaveArmDay` fires at
  08:55 the checkout is on `autonomous/<date>-daily`, not `master`. Work committed there is fine —
  it reaches `master` through the merge gate — but a session that believes it is on `master` will
  describe its own commits wrongly in a handoff.
- **A dirty tree you did not create is the window mid-iteration, not a problem.** Do not clean it,
  stash it, or commit it. Stage **only** your own explicit paths (the repo rule anyway), commit
  promptly, and push — the exposure window matters, because the playbook tells the window never to
  end an iteration with a dirty tree and unexpected modified files can confuse it.
- **Do not leave your own edits uncommitted while a window runs**, and do not leave them uncommitted
  going into 22:55 — `arm-cycle.ps1` refuses on a dirty tree and the whole night is lost.
- **The same trap has a MORNING mouth at 08:55, and an interactive session is the likeliest thing
  to walk into it** *(2026-09-09, walked into)*. `AgentWeaveArmDay` runs the identical
  `arm-cycle.ps1:118-125` check. A session that commits at 08:45 to leave a clean tree, then opens
  an editor at 08:50, is dirty at 08:55:01 and the **whole day window is skipped** — silently, to a
  hidden console. Ten minutes earlier that same session had written *"committed before 08:55
  deliberately, arm-cycle.ps1:118 refuses on a dirty tree"* into a commit message. Knowing the rule
  is not the same as holding the tree clean **through** the firing instant. **Between about 08:50
  and 08:56, and again 22:50–22:56, either be committed or do not be editing.**
  Detect it with `(Get-ScheduledTaskInfo -TaskName AgentWeaveArmDay).LastTaskResult` — **3 means it
  refused.** Corroborate before believing it: `STATE-day.json` and `driver-day.log` will still carry
  *yesterday's* mtime, and `Get-ScheduledTask AgentWeaveDayLoop` will not exist at all.
- **Re-arming a missed window by hand needs `-StartAt`; a plain re-arm fails in a way that reads
  like a bug** *(2026-09-09)*. `arm-cycle.ps1 -Window day` after 09:00 computes the *next* 09:00 —
  tomorrow — and `install-driver.ps1` dies with `Start 2026-09-10 09:00 is not before stop
  2026-09-09 17:00; the run would have no window.` The override exists and its own comment says it
  is for exactly this: `powershell -File .claude/loops/arm-cycle.ps1 -Window day -StartAt "09:15"`.
  **The failed first attempt is not harmless** — it writes, commits and pushes `STATE-day.json` and
  the day log before the installer runs, so the repo briefly carries an armed-looking state with no
  registered driver. Re-running with `-StartAt` reconciles it (`nothing to commit (state
  unchanged)`), so recover forward rather than reverting the arm commit.
- Concurrent commits interleave without incident: the window's next commit simply takes yours as
  parent. Observed working on 2026-09-08 09:20, with `e964226` landing between the window's
  `101f836` and its following iteration.

- **`git commit -F -` with a heredoc inside an `&&` chain failed once with
  `warning: here-document at line 1 delimited by end-of-file` and `Aborting commit due to empty
  commit message`** *(2026-09-08)*. It had worked several times in the same session, so it is
  intermittent rather than categorical. **The reliable form for a long message: write it to a file
  in the scratchpad with the Write tool, then `git commit -F <that path>`.** Costs one extra tool
  call and never loses a composed message.

## Measuring this repository's own documents

*Added 2026-09-08, after an instrument that read `scripts/drive/FINDINGS.md` was wrong four
separate ways in one afternoon. These are about measuring prose, not about any one script.*

- **Writing a census INTO the file it measures changes the census.** Measured, not theorised: the
  classification table published in `c18cb6f` matched the tree it was taken from (`c18cb6f~1`) and
  was **already stale in the commit that carried it**, because the prose naming `F32`, `F108`,
  `F161`, `F162`, `F187` and `F272` beside resolution words fed the cross-section arm six new
  matches. `FINDINGS.md` is an input to `scripts/classify_findings.py`. **Put computed counts
  somewhere the tool does not read** — `ROADMAP.md` — and leave a pointer in the measured file.
- **Reconcile two counts of the same thing the moment they disagree — the gap is the finding.**
  `grep -c` said **297** F-headings and the script said **271**; that 26 sat unexplained for a day.
  It was not a rounding difference: 26 findings had **no section at all** because their headings
  carry no `(A)`-style severity, and **one of them, F77, is open**. No census on that page had ever
  counted it.
- **An instrument that segments a document must be checked against the document's STRUCTURE, not
  only its vocabulary.** The same missing-parenthetical bug meant an unseen heading did not *end*
  the previous section, so **F71's section absorbed F72–F86, 1,223 lines**, and seven findings took
  their verdict from a neighbour's status line — four on the arm the script called trustworthy.
  Vocabulary tests (does "not fixed" read as fixed?) all passed while this was happening.
- **A self-report that does not recompute is a claim, not a measurement.** The same script printed
  *"3 of 5 hand-checked FALSE"* as a **string literal**. By then the true count was 7. This is the
  banner disease in Python: a sentence asserting a fact nobody re-derived.
- **`^#{1,4} F\d+ \(` is not a safe heading pattern for `FINDINGS.md`.** 46 headings lack a
  parenthetical, and headings also come in `(A-)`, `(—)`, `(B?)`, `(C, open)`,
  `(new, severity **B**)`, `(C, was B)`, `(RETRACTED, was B)` and `(C, harness)` forms.
- **A spawned review agent's findings are leads, not verdicts — check them too.** An Opus review
  correctly found both structural defects above, and was **wrong about the cause** of the third,
  asserting the published table *"never reproduced"*. It had reproduced, one commit earlier; the
  agent had not thought to test the parent. Both halves mattered, and only measuring separated them.

- **Backticks in a double-quoted `git commit -m` execute.** *(Re-confirmed 2026-09-08, having
  already been in this file.)* It cost a failed commit with
  `error: pathspec 'the' did not match any file(s)` and `relative: command not found`, because the
  message contained `` `uvicorn hub.main:app` ``. The ledger entry above was right and was not read
  first. **Use `git commit -F <file>` for any message containing backticks — which, in this
  repository, is most of them.**
- **A test for a guard is decorative unless the guard's output is the ONLY route to the asserted
  verdict** *(2026-09-09, found by a surviving mutation)*. Two tests written for
  `scripts/classify_findings.py`'s quotation stripping asserted `RESOLVED` on a fixture that also
  carried a `**Status:** fixed` line. `RESOLVED` is decided before `OPEN`, so both passed with
  `dequote` disabled entirely — the mutation survived and the tests proved nothing. **The fix is in
  the fixture, not the assertion: remove every competing signal, then assert the weaker claim**
  (`!= "OPEN"` rather than `== "RESOLVED"`). Generalises past this file: when a function picks a
  verdict by precedence, a fixture that satisfies a *higher*-precedence branch cannot test a lower
  one.
- **Widening a guard can reveal that an incidental property of the old form was load-bearing**
  *(2026-09-09, cost six verdicts and two wrong diagnoses)*. `NEG_BEFORE` was
  `\b(not|never|...)\W{0,12}$` — which cannot span a word, so it was **line-local by accident.**
  Widened to tolerate intervening words, a finding's *title* immediately reached across a blank line
  to negate its own `**Status:** fixed`, and F16/F27/F46/F58/F95/F100 silently became `UNCLASSIFIED`.
  Two successive hypotheses about the cause were wrong before the pre-match window was printed.
  **When widening a pattern, enumerate what the narrow form was incidentally preventing, and state
  the constraint you intended explicitly** — here, the line bound — rather than inheriting it.
- **Debug a regex by printing the actual matched text and its pre-window, not by reasoning about the
  pattern** *(2026-09-09)*. Two plausible explanations for the six lost verdicts were constructed and
  committed to before the 40 characters preceding the match were printed; both were wrong. One
  `print(repr(pre))` settled it immediately.
- **An `ORDER:` line may name work that is neither a change directory nor an `F<n>`, provided the
  same section defines it** *(2026-09-09, driven)*. Four items — `R1-ratchets`,
  `R2-archive-collision`, `R34-model-catalog`, `DAY1-constraints` — were appended to the line with a
  definition block below giving each a target, a done-condition and its source verdict. The night
  window resolved and completed all four. The format example in `spec-queue/README.md` shows only
  change names and finding numbers; it is an example, not the grammar. **What the window needs is
  resolvability, not a registered id.**
- **A merged branch stops being merged the moment you commit to it again, and
  `arm-cycle.ps1` reads that at firing time, not at merge time** *(2026-09-09, a prediction made and
  then falsified by the predictor)*. After fast-forwarding `master` to the cycle branch, the arm was
  expected to cut a fresh `autonomous/<today>-daily`. A later commit on the branch put it one ahead
  of `master`, so `git branch --merged master` no longer listed it, `$openCycle` found it, and the
  night **continued the old branch**. Both behaviours are correct; the state is read at 22:55.
- **`git rm --cached <path>` followed by `rm <path>` makes a later `git add <path>` fail**
  *(2026-09-09)*: `fatal: pathspec '<path>' did not match any files`, which aborts an `&&` chain. The
  deletion is already staged by the `git rm --cached`, so the `git add` is both unnecessary and
  fatal. To stage a deletion of a tracked file, `git rm <path>` alone is enough.

## RESOLVED

Kept because "we used to believe this" is worth knowing, and because an entry that quietly
disappears is indistinguishable from one that was forgotten.

- **`npm run lint` does not work at all** *(believed 2026-08-08 → 2026-09-04)*. ESLint 9 needed a
  flat config and the repo had none, so it failed before linting anything; `npx tsc --noEmit` was
  the real check. **RESOLVED: `hub/ui/eslint.config.js` now exists** (verified 2026-09-04). CI
  lints for real again — treat a lint failure as a finding, not as this known breakage.
- **The default `python` on PATH has no pytest** *(believed 2026-08 → 2026-09-04)*. **RESOLVED,
  and replaced by a worse fact:** it now has pytest 9.1.1 and produces phantom failures instead of
  erroring. See the Python section — still use `py -3.11`.
- **`npx openspec …` is required** *(believed 2026-08)*. **RESOLVED:** `openspec` is on PATH
  directly (verified 2026-09-04).
